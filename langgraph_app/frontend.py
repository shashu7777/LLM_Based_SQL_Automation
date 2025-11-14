import streamlit as st
from app import chatbot, retrieve_all_threads, get_conversation_summary, get_response_from_chatbot
from langchain_core.messages import HumanMessage
import uuid
import collections
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage # Import necessary types

st.markdown("""
            <style>
            /* Style for all chat conversation buttons */
.stButton button {
    width: 100%;
    text-align: left;
    margin-top: 5px;
    padding: 10px 12px;
    border-radius: 6px;
    border: 1px solid #30363d; 
    background-color: #161b22;
    color: #c9d1d9;
    transition: background-color 0.2s, border 0.2s;
    line-height: 1.2;
}

/* Hover state */
.stButton button:hover {
    background-color: #21262d;
    color: #f0f6fc;
    border-color: #58a6ff;
}

/* New Chat Button (separate styling, ensure visibility) */
[data-testid="stSidebar"] [data-testid="stButton"][key="new_chat_btn"] button {
    background-color: #30363d;
    color: #58a6ff;
    border: 1px solid #58a6ff;
    font-weight: bold;
    margin-bottom: 15px;
}

/* <<<< ACTIVE Conversation Highlight FIX (Adjacent Sibling) >>>> */
            /* This targets the button that follows the specific data-active="true" markdown marker */
            /* It uses the adjacent sibling selector (+) on the div's parent container */
            [data-testid="stSidebar"] div[data-active="true"] + [data-testid="stVerticalBlock"] [data-testid="stButton"] button {
                 background-color: #30363d !important;
                 color: #58a6ff !important;
                 font-weight: bold !important;
                 border: 3px solid #58a6ff !important; /* Thick, distinct border */
                 padding-left: 10px !important;
            }
            </style>""", unsafe_allow_html=True)

st.set_page_config(page_title="🧠 SQL Assistant", layout="centered")

def generate_thread_id():
    thread_id = str(uuid.uuid4())
    return thread_id

def add_thread(thread_id, summary=None):
    if summary is not None:
        # Prepend the new conversation to the dictionary (latest first)
        new_dict = collections.OrderedDict([(thread_id, summary)])
        new_dict.update(st.session_state['chat_threads'])
        st.session_state['chat_threads'] = new_dict

def reset_chat():
    thread_id = generate_thread_id()
    st.session_state['thread_id'] = thread_id
    st.session_state['messages'] = []

def load_conversation(thread_id):
    state = chatbot.get_state(config={'configurable': {'thread_id': thread_id}})
    return state.values.get('messages', [])
    

# ... in frontend.py

def switch_chat(thread_id):
    """Switches to another existing chat thread."""
    st.session_state['thread_id'] = thread_id

    # Load from LangGraph memory
    messages = load_conversation(thread_id)

    temp_messages = []
    for msg in messages:
        # ⚠️ Only include HumanMessage (user) and AIMessage (final assistant response)
        if isinstance(msg, HumanMessage):
            role = 'user'
            content = msg.content
            temp_messages.append({'role': role, 'content': content})
        elif isinstance(msg, AIMessage):
            # Only use the content if it's not a tool call (which is handled by Streamlit's display)
            # and is an actual text response.
            if msg.content:
                role = 'assistant'
                content = msg.content
                if '<br>' in content:
                    # 1. Remove all <br> tags (case-insensitive)
                    content = content.replace('<br>', ' ').replace('<BR>', ' ')

                temp_messages.append({'role': role, 'content': content})


    st.session_state['messages'] = temp_messages
    st.session_state._old_state = st.session_state.to_dict()
    st.rerun()
    
#--------------- Session Setup--------------------------- 
if "messages" not in st.session_state:
    st.session_state["messages"] = []
if "thread_id" not in st.session_state:
    st.session_state["thread_id"] =generate_thread_id()
if 'chat_threads' not in st.session_state:
    retrieved_threads = retrieve_all_threads()
    st.session_state['chat_threads'] = collections.OrderedDict(retrieved_threads)    
    print(st.session_state['chat_threads'])

# ---------------- SIDEBAR ----------------
st.sidebar.title("⚙️ Options")

# "New Chat" button
if st.sidebar.button("🆕 New Chat"):
    reset_chat()
    st.rerun()
    
current_thread_id = st.session_state['thread_id']
    
for thread_id, summary in st.session_state['chat_threads'].items():
    print("current id:", current_thread_id)
    print("thread_id:", thread_id)
    print("summary:",summary)
    is_active = (thread_id == current_thread_id)
    print(is_active)
    
    # 1. Inject the data-active attribute marker (st.markdown div)
    # The CSS uses the adjacent sibling selector (+) to style the button that FOLLOWS this div.
    if is_active:
         st.sidebar.markdown('<div data-active="true"></div>', unsafe_allow_html=True)
         print("mmm")
    else:
         st.sidebar.markdown('<div data-active="false"></div>', unsafe_allow_html=True)
         print("bbbbb")

    # 2. Render the actual st.button.
    # This button is styled by the CSS based on the marker above it.
    if st.sidebar.button(summary, key=f"sidebar_btn_{thread_id}"):
        
        
            print("mmmmmm")
            switch_chat(thread_id)     
  
#---------------- Main UI Starts-------------------------
# Optional: You can later show DB connection info here
# st.sidebar.info("Connected to MySQL → shopdb as root")
# ---------------- Main UI Starts -------------------------
st.title("🧠 SQL Assistant")

# Display existing conversation
for message in st.session_state['messages']:
    with st.chat_message(message['role']):
        st.markdown(message['content'])

# Input box at bottom
if user_input := st.chat_input("Type your message..."):
    is_first_turn = len(st.session_state['messages']) == 0

    # Append and display user message
    st.session_state['messages'].append({'role': 'user', 'content': user_input})
    st.chat_message('user').markdown(user_input)

    with st.spinner("Thinking..."):
        response = get_response_from_chatbot(user_input, st.session_state["thread_id"])

    # ✅ Append only once and render once
    st.session_state['messages'].append({'role': 'assistant', 'content': response})
    st.chat_message('assistant').markdown(response)

    if is_first_turn:
        new_summary = get_conversation_summary(st.session_state['thread_id'])
        add_thread(st.session_state['thread_id'], summary=new_summary)
        st.rerun()

        
    # Display assistant response
    # st.chat_message("assistant").markdown(response)
    # st.session_state["messages"].append({"role": "assistant", "content": response})
