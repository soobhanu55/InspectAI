"""Entry point of the MQTT -> Redis Stream bridge (see streaming/mqtt.py)."""
from __future__ import annotations

import os
import signal

import redis
import structlog

from streaming.broker import RedisStreamBroker
from streaming.mqtt import MqttBridge, connect, new_client

logger = structlog.get_logger()


def main() -> None:  # pragma: no cover - wiring, exercised by the docker-compose stack and the CI integration test
    bridge = MqttBridge(RedisStreamBroker(redis.Redis.from_url(os.environ["REDIS_URL"])))
    client = new_client(os.environ.get("MQTT_CLIENT_ID", "mqtt-bridge"))
    bridge.attach(client)
    client.reconnect_delay_set(min_delay=1, max_delay=30)  # paho reconnects with backoff after a broker restart
    connect(client, os.environ.get("MQTT_URL", "mqtt://localhost:1883"))
    signal.signal(signal.SIGTERM, lambda *_: client.disconnect())
    client.loop_forever(retry_first_connection=True)


if __name__ == "__main__":  # pragma: no cover
    main()
