import os
import chainlit as cl
import base64
import openai

from dotenv import load_dotenv
from langsmith import traceable
from langsmith.wrappers import wrap_openai
from openai import OpenAI
from prompts import SYSTEM_PROMPT

# Load environment variables
load_dotenv()

#setup model options
configurations = {
    "openai_gpt-4": {
        "endpoint_url": "https://api.openai.com/v1",
        "api_key": os.getenv("OPENAI_API_KEY"),
        "model": "gpt-4o-mini"
    }
}
config_key ="openai_gpt-4"

# Get selected configuration
config = configurations[config_key]

# Initialize the OpenAI async client
client = wrap_openai(openai.AsyncClient(api_key=config["api_key"], base_url=config["endpoint_url"]))

# general model settings
model_kwargs = {
    "model": config["model"],
    "temperature": 0.3,
    "max_tokens": 500
}

#allow toggle of system prompt

ENABLE_SYSTEM_PROMPT = True

@traceable
@cl.on_message
async def on_message(message: cl.Message):
    # Maintain an array of messages in the user session
    message_history = cl.user_session.get("message_history", [])

    # add system prompt in history if not exists
    if ENABLE_SYSTEM_PROMPT and (not message_history or message_history[0].get("role") != "system"):
        system_prompt_content = SYSTEM_PROMPT
        message_history.insert(0, {"role": "system", "content": system_prompt_content})

# Processing images if they exist
    images = [file for file in message.elements if "image" in file.mime] if message.elements else []

    if images:
        # Read the first image and encode it to base64
        with open(images[0].path, "rb") as f:
            base64_image = base64.b64encode(f.read()).decode('utf-8')
        message_history.append({
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": message.content if message.content else "What’s in this image?"
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{base64_image}"
                    }
                }
            ]
        })
    else:
        # add in user information and current message for ease of use in API call
        message_history.append({"role": "user", "content": message.content})

    # send initial response as an empty string
    response_message = cl.Message(content="")
    await response_message.send()

    # send message history along to model and stream response
    stream = await client.chat.completions.create(messages=message_history,
                                                  stream=True, **model_kwargs)
    # send over parts of response as stream as they're ready
    async for part in stream:
        if token := part.choices[0].delta.content or "":
            await response_message.stream_token(token)
    # finish the response message; no more updates
    await response_message.update()

    # Record the AI's response in the history
    message_history.append({"role": "assistant", "content": response_message.content})
    cl.user_session.set("message_history", message_history)
    await response_message.update()

