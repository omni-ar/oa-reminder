# agent_test.py

import torch
# --- Back to the original, compatible LLM wrapper ---
from langchain_huggingface import HuggingFacePipeline
from langchain.agents import tool, create_react_agent, AgentExecutor
from langchain.prompts import PromptTemplate
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline

from services.situational_gen import generate_situational_question

# STEP 1: DEFINE OUR TOOLS
@tool
def situational_question_generator_tool():
    """
    Use this tool to generate a unique situational or behavioral interview question
    for a software engineer. This tool takes no input.
    """
    # Call the new function and extract just the question string for the agent
    result = generate_situational_question(use_ai=True) 
    return result["question"]

tools = [situational_question_generator_tool]

# STEP 2: LOAD THE "BRAIN" - OUR LLM
print("Loading the agent's 'brain' (Phi-3 Mini model)...")
model_id = "microsoft/Phi-3-mini-4k-instruct"

model = AutoModelForCausalLM.from_pretrained(
    model_id,
    torch_dtype=torch.bfloat16,
    load_in_4bit=True,
    trust_remote_code=True
)
tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)

pipe = pipeline(
    "text-generation",
    model=model,
    tokenizer=tokenizer,
    max_new_tokens=256,
    temperature=0.1,
)

# --- Back to the original, compatible LLM wrapper ---
llm = HuggingFacePipeline(pipeline=pipe)

print("✅ Brain loaded successfully.")

# STEP 3: CREATE A HIGHLY-SPECIFIC PROMPT WITH AN EXAMPLE
# This new prompt includes a perfect example of the thought process,
# which helps the model avoid formatting mistakes.
prompt_template = """
You are a helpful assistant that generates interview questions. Answer the user's request using the available tools.

You have access to the following tools:
{tools}

Use the following format for your thought process:

Thought: The user wants me to do something. I need to figure out which tool to use.
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action. If there is no input, use an empty string.
Observation: the result of the action.

### EXAMPLE ###
Question: Can you get me a situational question?
Thought: The user wants a situational question. The tool `situational_question_generator_tool` is perfect for this. It takes no input.
Action: situational_question_generator_tool
Action Input: 
Observation: A team member has been consistently underperforming and is jeopardizing the project timeline. How would you address this situation?
Thought: I now have the final answer.
Final Answer: A team member has been consistently underperforming and is jeopardizing the project timeline. How would you address this situation?
### END OF EXAMPLE ###

Now, begin!

Question: {input}
Thought:{agent_scratchpad}
"""

prompt = PromptTemplate.from_template(prompt_template)

# STEP 4: CREATE AND RUN THE REACT AGENT
agent = create_react_agent(llm, tools, prompt)

agent_executor = AgentExecutor(
    agent=agent,
    tools=tools,
    verbose=True,
    handle_parsing_errors=True,
    max_iterations=5
)

print("\n--- Invoking the agent ---")
goal = "Please generate one situational interview question for me."
result = agent_executor.invoke({"input": goal})

print("\n--- Agent's Final Answer ---")
print(result['output'])