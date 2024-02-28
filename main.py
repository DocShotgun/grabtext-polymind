import json
import os
from pathlib import Path
from urllib.request import Request, urlopen

from curl_cffi import requests
from PyPDF2 import PdfReader
from trafilatura import extract

# Read config
script_dir = Path(os.path.abspath(__file__)).parent
conf_path = script_dir / "config.json"
with open(conf_path, "r") as config_file:
    config = json.load(config_file)
ctx_alloc = config.get("ctx_alloc", 0.5)


def get_pdf_from_url(url):
    """
    :param url: url to get pdf file
    :return: PdfReader object
    """
    remote_file = urlopen(Request(url)).read()
    memory_file = io.BytesIO(remote_file)
    pdf_file = PdfReader(memory_file)
    return pdf_file


def simple_scrape(url):
    try:
        response = requests.get(url, timeout=3, impersonate="chrome110")
        content_type = response.headers.get("content-type")
        if url.endswith(".pdf") or "application/pdf" in content_type:
            text = ""
            for x in get_pdf_from_url(url).pages:
                text += x.extract_text()
        else:
            text = extract(response.text)
        text = text.strip()
        # text = text.replace("\n", "")
        return text
    except Exception as e:
        print(e)
        return "Error: Requested site couldn't be viewed. Please inform in your response that the informations may not be up to date or correct."


def main(params, memory, infer, ip, Shared_vars):
    # Definitions for API-based tokenization
    API_ENDPOINT_URL = Shared_vars.API_ENDPOINT_URI
    if Shared_vars.TABBY:
        API_ENDPOINT_URL += "v1/completions"
    else:
        API_ENDPOINT_URL += "completion"

    def tokenize(input):
        payload = {
            "add_bos_token": "true",
            "encode_special_tokens": "true",
            "decode_special_tokens": "true",
            "text": input,
            "content": input,
        }
        request = requests.post(
            API_ENDPOINT_URL.replace("completions", "token/encode")
            if Shared_vars.TABBY
            else API_ENDPOINT_URL.replace("completion", "tokenize"),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {Shared_vars.API_KEY}",
            },
            json=payload,
            timeout=360,
        )
        return request.json()["length"] if Shared_vars.TABBY else len(
            request.json()["tokens"]
        ), request.json()["tokens"]

    def decode(input):
        payload = {
            "add_bos_token": "false",
            "encode_special_tokens": "false",
            "decode_special_tokens": "false",
            "tokens": input,
        }
        request = requests.post(
            API_ENDPOINT_URL.replace("completions", "token/decode")
            if Shared_vars.TABBY
            else API_ENDPOINT_URL.replace("completion", "detokenize"),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {Shared_vars.API_KEY}",
            },
            json=payload,
            timeout=360,
        )
        return (
            request.json()["text"] if Shared_vars.TABBY else request.json()["content"]
        )

    def shorten_text(text, max_tokens):
        currlen, tokens = tokenize(text)
        if currlen < max_tokens:
            return text, tokenize(text)
        else:
            diff = abs(currlen - max_tokens)
            tokens = tokens[:-diff]
            currlen = len(tokens)
        return decode(tokens), currlen

    URLs_raw = params.get("urls")
    URLs = URLs_raw.split(",")
    message = ""

    for URL in URLs:
        text = simple_scrape(URL.strip())
        if len(message) > 0:
            message = message + "\n***\n" + URL.strip() + "\n"
        message += text

    # Handle unsuccessful search
    if len(message) == 0:
        print("No fetch results")
        return "No fetch results received, notify the user of this and respond based on your knowledge"

    # Prevent RAG content from taking up too much of the context
    if ctx_alloc == -1:
        print(message)
    else:
        print("BEFORE SHORTENING:", message)
        message, token_count = shorten_text(
            message, int((Shared_vars.config.ctxlen * ctx_alloc) // len(URLs))
        )
        print("AFTER SHORTENING:", message)

    return "<fetch_results>:\n" + message + "</fetch_results>"


if __name__ == "__main__":
    main(params, memory, infer, ip, Shared_vars)
