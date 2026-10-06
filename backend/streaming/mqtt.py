"""MQTT edge transport: cameras and gateways publish frames to an MQTT broker (the protocol factory equipment speaks);
a bridge on the plant side republishes them onto the Redis Stream that the inspection workers consume.

    camera / gateway --MQTT QoS 1--> Mosquitto --> MqttBridge --> Redis Stream (consumer group) --> workers

Why both: MQTT is what PLCs, gateways and cameras on a constrained line network speak (small headers, last-will and
reconnect semantics, topic hierarchies); Redis Streams gives the plant side consumer groups, acknowledgement and
reclaim. Topics: factory/<line>/<machine>/frames. A message is one frame: a 4-byte big-endian header length, a JSON
header (frame_id, machine, part_type, captured_at, meta) and then the raw image bytes.

    python -m streaming.mqtt_bridge          # reads MQTT_URL and REDIS_URL
"""
from __future__ import annotations

import json
import struct
from collections import defaultdict
from urllib.parse import urlparse

import structlog

from streaming.broker import Broker, Frame

logger = structlog.get_logger()

TOPIC_FILTER = "factory/+/+/frames"
MAX_MESSAGE_BYTES = 8 * 1024 * 1024  # a camera frame beyond this is not a frame


class BadMessage(ValueError):
    pass


def topic_for(frame: Frame, line: str = "line1") -> str:
    return f"factory/{line}/{frame.machine}/frames"


def encode_frame(frame: Frame) -> bytes:
    header = json.dumps({"frame_id": frame.frame_id, "machine": frame.machine, "part_type": frame.part_type,
                         "captured_at": frame.captured_at, "meta": frame.meta}).encode("utf-8")
    return struct.pack(">I", len(header)) + header + frame.image


def decode_frame(payload: bytes) -> Frame:
    if len(payload) > MAX_MESSAGE_BYTES:
        raise BadMessage("message too large")
    if len(payload) < 4:
        raise BadMessage("message shorter than its length prefix")
    (n,) = struct.unpack(">I", payload[:4])
    if n == 0 or 4 + n > len(payload):
        raise BadMessage("header length does not fit the message")
    try:
        h = json.loads(payload[4:4 + n])
        return Frame(frame_id=str(h["frame_id"]), machine=str(h["machine"]), part_type=str(h["part_type"]),
                     image=payload[4 + n:], captured_at=float(h["captured_at"]), meta=dict(h.get("meta", {})))
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise BadMessage(f"bad header: {exc}") from exc


def new_client(client_id: str):
    import paho.mqtt.client as mqtt

    return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)


def connect(client, url: str, keepalive: int = 30) -> None:
    u = urlparse(url)
    if u.username:
        client.username_pw_set(u.username, u.password)
    client.connect(u.hostname or "localhost", u.port or 1883, keepalive)


class MqttFramePublisher:
    """Camera side: publish(frame) sends one frame at QoS 1. Has the same publish() as a Broker, so
    streaming.producer.publish_stream can feed MQTT instead of Redis."""

    def __init__(self, client, line: str = "line1"):
        self.client, self.line = client, line
        self._last = None

    def publish(self, frame: Frame) -> str:
        self._last = self.client.publish(topic_for(frame, self.line), encode_frame(frame), qos=1)
        return str(self._last.mid)

    def flush(self, timeout: float = 10.0) -> None:
        """Wait until the broker has acknowledged the last frame (QoS 1 acknowledgements arrive in order)."""
        if self._last is not None:
            self._last.wait_for_publish(timeout)


class MqttBridge:
    """Plant side: every frame message becomes an entry on the broker (the Redis stream). Malformed messages are
    counted and dropped: a bad publisher must not be able to stop the line."""

    def __init__(self, broker: Broker):
        self.broker = broker
        self.stats = defaultdict(int)

    def on_message(self, client, userdata, msg) -> None:
        try:
            frame = decode_frame(bytes(msg.payload))
        except BadMessage as exc:
            self.stats["rejected"] += 1
            logger.warning("mqtt_message_rejected", topic=msg.topic, reason=str(exc))
            return
        self.broker.publish(frame)
        self.stats["forwarded"] += 1

    def on_connect(self, client, userdata, flags, reason_code, properties=None) -> None:
        client.subscribe(TOPIC_FILTER, qos=1)  # (re)subscribe on every connect, so a broker restart does not silence us
        logger.info("mqtt_connected", reason=str(reason_code))

    def attach(self, client) -> None:
        client.on_connect, client.on_message = self.on_connect, self.on_message
