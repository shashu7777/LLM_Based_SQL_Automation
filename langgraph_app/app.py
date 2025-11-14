from langgraph.graph import StateGraph, START, END
from typing import TypedDict, Annotated
from langchain_core.messages import BaseMessage, HumanMessage,SystemMessage
from langgraph.graph.message import add_messages
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError
import pymysql
from langchain_ollama import OllamaLLM
from langchain_google_genai import ChatGoogleGenerativeAI
from tabulate import tabulate
from langchain_core.tools import tool
from langgraph.prebuilt import ToolNode, tools_condition
from dotenv import load_dotenv
import os
from langgraph.checkpoint.sqlite import SqliteSaver
import sqlite3
import re
import ast
from langchain_openai import ChatOpenAI

import asyncio
from mcp_client import MCPClientWrapper

load_dotenv()
google_api_key = os.getenv("GOOGLE_API_KEY")
openai_api_key = os.getenv("OPENAI_API_KEY")
# ---------------- MCP CLIENT ----------------
mcp = MCPClientWrapper()
try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)


# ---------------- TOOL WRAPPERS ----------------
@tool
def connect_to_db(db_type:str, username:str, password:str, database_name:str) -> dict:
    """Connect to database (only if not connected yet)."""
    print("🔌 Calling connect_to_db...")
    return loop.run_until_complete(mcp.call_tool("connect_to_db", {
        "db_type": db_type,
        "host": "localhost",
        "username": username,
        "password": password,
        "database_name": database_name
    }))
    


@tool
def get_schema() -> dict:
    """Retrieve database schema (used before query generation)."""
    print("📘 Calling get_schema...")
    return loop.run_until_complete(mcp.call_tool("get_schema"))


@tool
def execute_query(query: str) -> dict:
    """Execute SQL query and return the result."""
    print("🚀 Calling execute_query...")
    return loop.run_until_complete(mcp.call_tool("execute_query", {"query": query}))

@tool
def generate_sql_query(request: str) -> dict:
    """Generate an SQL query from a natural language request using schema context."""
    print("🧠 Calling generate_sql_query...")


    prompt = f"""
    You are an expert SQL assistant. generate the SQL query based on the user request

    for this request:
    {request}
    """

    query_response = model.invoke([HumanMessage(content=prompt)])
    return {"query": query_response.content.strip()}


tools = [connect_to_db, get_schema, execute_query,generate_sql_query]


# ---------------- LLM SETUP ----------------
gemini_model=ChatGoogleGenerativeAI(
    model='gemini-2.5-flash',
    temperature=0.7,
    google_api_key=google_api_key)

model = ChatOpenAI(
    openai_api_key=openai_api_key,
    model_name="openai/gpt-oss-120b",
    openai_api_base="https://api.groq.com/openai/v1",  # point to Groq
    temperature=0.7,
)


llm_with_tools = model.bind_tools(tools, parallel_tool_calls=False)


# ---------------- STATE DEFINITION ----------------
class SQLState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    last_query: str
    # connected: bool


# ---------------- NODES ----------------
def chat_node(state: SQLState):
    """Handles reasoning and decides if a tool call is needed."""
    messages = state["messages"]
    response = llm_with_tools.invoke(messages)
    # Store the last SQL query (for later execution)
    if "SELECT" in response.content.upper() or "INSERT" in response.content.upper() or "UPDATE" in response.content.upper():
        state["last_query"] = response.content

    return {"messages": [response]}


tool_node = ToolNode(tools)


# ---------------- GRAPH SETUP ----------------
graph = StateGraph(SQLState)
graph.add_node("chat_node", chat_node)
graph.add_node("tools", tool_node)

graph.add_edge(START, "chat_node")
graph.add_conditional_edges("chat_node", tools_condition)
graph.add_edge("tools", "chat_node")


# ---------------- PERSISTENCE ----------------
conn = sqlite3.connect("chatbot_memory.db", check_same_thread=False)
checkpointer = SqliteSaver(conn=conn)

chatbot = graph.compile(checkpointer=checkpointer)


# ---------------- MAIN EXECUTION ----------------
thread_id = "sql_thread_1"
config = {"configurable": {"thread_id": thread_id}}

state = checkpointer.list(None)
if not state:
    chatbot.update_state(
        thread_id,
        {
            "messages": [
                SystemMessage(content="""
                    You are an expert SQL assistant for MySQL.

                    - Use `connect_to_db` only once per session.
                    - Use `get_schema` to understand DB structure before generating queries.
                    - After generating the query stop right there and ask the user to execute that query or not.
                    - NEVER execute queries without explicit user confirmation (e.g., "run", "execute", "try it").
                    - If user says "explain", describe the query without using tools.
                    - Remember the last generated SQL query so that it can be executed later.
                """)
            ],
            "last_query": "",
            "connected": False,
        }
    )
    
def get_response_from_chatbot(user_input: str, thread_id: str):
    """
    Wrapper function to send a user message to the chatbot and get the response.
    Maintains conversation using thread_id.
    """
    config = {"configurable": {"thread_id": thread_id}}
    result = chatbot.invoke({"messages": [HumanMessage(content=user_input)]}, config=config)

    # ✅ Extract readable message safely
    ai_message = result["messages"][-1]

    # Case 1: simple text reply
    if hasattr(ai_message, "content") and isinstance(ai_message.content, str):
        return ai_message.content.strip()

    # Case 2: CallToolResult or structured message
    if hasattr(ai_message, "content") and isinstance(ai_message.content, list):
        try:
            # If it's a list of content objects, join the textual parts
            text_parts = []
            for item in ai_message.content:
                if hasattr(item, "text"):
                    text_parts.append(item.text)
                elif isinstance(item, dict) and "text" in item:
                    text_parts.append(item["text"])
            return "\n".join(text_parts).strip()
        except Exception as e:
            return f"[⚙️ Internal tool output suppressed: {str(e)}]"

    # Default fallback
    return str(ai_message)

#---------------------user conversation summary----------------------------------------------
def get_first_user_message_content(thread_id: str) -> str | None:
    """Retrieves the content of the first HumanMessage for a thread."""
    try:
        # Load the thread state
        state = chatbot.get_state(config={'configurable': {'thread_id': thread_id}})
        messages = state.values.get('messages', [])
        
        # Find the first HumanMessage content
        for msg in messages:
            if isinstance(msg, HumanMessage) and msg.content:
                return msg.content.strip()
        return None
    except Exception:
        # Handle cases where the thread_id might not exist in the checkpoint yet
        return None
    
    
def generate_summary_from_message(first_message_content: str) -> str:
    """Generates a short, conversational summary from the first user message using the LLM."""
    if not first_message_content:
        return 'Empty Chat'

    prompt = (
        "You are a helpful assistant. "
        "Summarize the following user message into a short (under 7 words), "
        "descriptive phrase suitable for a chat title. Do not include quotes or end punctuation."
        f"\n\nUser Message: {first_message_content}"
    )
    
    try:
        response = gemini_model.invoke(prompt)
        summary = response.content.strip().replace('.', '').replace('"', '')
        # Simple length check fallback
        return summary if len(summary.split()) <= 7 and len(summary) > 3 else first_message_content[:30] + '...'
    except Exception:
        return 'Conversation Summary'    
    
    
def get_conversation_summary(thread_id: str) -> str:
    """Gets the short summary for a thread, generating it if necessary."""
    first_message = get_first_user_message_content(thread_id)
    
    if first_message:
        return generate_summary_from_message(first_message)
    else:
        # Fallback for empty chats
        return f'New Chat {thread_id[:4]}'
    
    
# mapping thread_id to its summary string, which the frontend will use.
def retrieve_all_threads() -> dict[str, str]:
    """Retrieves all thread IDs and their conversational summaries."""
    all_thread_ids = set()
    for checkpoint in checkpointer.list(None):
        all_thread_ids.add(checkpoint.config['configurable']['thread_id'])
    
    # Generate summaries for all retrieved IDs
    thread_summaries = {}
    for thread_id in all_thread_ids:
        thread_summaries[thread_id] = get_conversation_summary(thread_id)
        
    # We return the dictionary of {thread_id: summary}
    return thread_summaries



if __name__ == "__main__":
    pass
