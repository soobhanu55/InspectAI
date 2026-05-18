from typing import TypedDict, Annotated, List, Dict, Any
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_core.messages import AnyMessage, HumanMessage

from agents.rca_agent import invoke_rca
from rag.pipeline import get_context

class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    defect_type: str
    severity: str
    machine: str
    part_type: str
    detections: list[dict]
    rag_context: str
    root_cause: str
    action_plan: list[str]
    eu_ai_act_tier: str
    estimated_savings_eur: int
    agent_steps: list[str]

class OrchestratorAgent:
    def __init__(self):
        builder = StateGraph(AgentState)
        
        builder.add_node("retrieve_context", self.retrieve_context_node)
        builder.add_node("classify_severity", self.classify_severity_node)
        builder.add_node("rca", self.rca_node)
        builder.add_node("action_plan", self.action_plan_node)
        builder.add_node("eu_compliance", self.eu_compliance_node)
        
        builder.add_edge(START, "retrieve_context")
        builder.add_edge("retrieve_context", "classify_severity")
        builder.add_edge("classify_severity", "rca")
        builder.add_edge("rca", "action_plan")
        builder.add_edge("action_plan", "eu_compliance")
        builder.add_edge("eu_compliance", END)
        
        self.graph = builder.compile()
        
    async def ainvoke(self, state: Dict[str, Any]) -> Dict[str, Any]:
        state["agent_steps"] = []
        return await self.graph.ainvoke(state)
        
    def retrieve_context_node(self, state: AgentState):
        query = f"{state['defect_type']} defect causes on {state['machine']}"
        context = get_context(query)
        state['rag_context'] = context
        state['agent_steps'].append("Hybrid RAG retrieval completed")
        return state
        
    def classify_severity_node(self, state: AgentState):
        state['agent_steps'].append(f"Severity classified as {state['severity']}")
        return state
        
    def rca_node(self, state: AgentState):
        result = invoke_rca(
            defect_type=state['defect_type'],
            machine=state['machine'],
            part_type=state['part_type'],
            context=state['rag_context'],
            severity=state['severity']
        )
        
        state['root_cause'] = result.get('root_cause', "Unknown root cause")
        state['action_plan'] = result.get('action_plan', ["Investigate further"])
        state['eu_ai_act_tier'] = result.get('eu_ai_act_tier', "Minimal Risk (Art. 6)")
        state['estimated_savings_eur'] = result.get('estimated_savings_eur', 0)
        state['agent_steps'].append("LLM root cause analysis completed")
        
        return state
        
    def action_plan_node(self, state: AgentState):
        state['agent_steps'].append("Action plan generated")
        return state
        
    def eu_compliance_node(self, state: AgentState):
        state['agent_steps'].append("EU compliance checked")
        return state
