from transformers import AutoTokenizer
import requests, json, time
import mlx.core as mx
model = "mlx-community/gemma-4-31b-it-6bit"
model = "mlx-community/gemma-4-31b-it-4bit"
mlxmodel = "gemma-4-31b-6-128"
mlxmodel = "gemma-4-31b-4-256"
tok = AutoTokenizer.from_pretrained(model)

filler= "the quick brown fox jumps over the lazy dog. "*13000
system="You are a helpful assistant."
tokens = tok.encode(filler)
tokens = tokens[:2**17]
print(f"Actual token count128: {len(tokens)}")

filler = tok.decode(tokens)
prompt128 = f"{filler}\n\nGiven everything above, summarize the key themes in one sentence"
final_count = len(tok.encode(prompt128))
print(f"final token count128: {final_count}")


filler = "the quick brown fox jumps over the lazy dog. " * 30000
system = "You are a helpful assistant."
tokens = tok.encode(filler)
tokens = tokens[: 2**18]
print(f"Actual token count256: {len(tokens)}")

filler = tok.decode(tokens)
prompt256 = f"{filler}\n\nGiven everything above, summarize the key themes in one sentence"
final_count = len(tok.encode(prompt256))
print(f"final token count256: {final_count}")


def test(prompt):
    print(f"Testing with prompt size {len(prompt)}")

    start = time.time()
    resp = requests.post(
        "http://localhost:8000/v1/chat/completions",
        json={
            "model": mlxmodel,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 200,
            "stream": False,
        },
    )

    elapsed = time.time() - start
    print(resp)
    print (resp.text)
    data = resp.json()
    print(f"Total time:    {elapsed:.1f}s")
    print(f"Usage:           {data}")

test(prompt256)
