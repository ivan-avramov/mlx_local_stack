"""C105(2): what does OpenWebUI echo back for a thinking turn, and does the worker's canonical
prediction match it? Three turns on one OpenWebUI chat (frontend request shape; the persisted
assistant content is echoed verbatim, as the frontend does), then the worker log for that chat id."""
import importlib.util, json, os, re, sys, time, uuid
spec = importlib.util.spec_from_file_location("gate", "$STACK_REPO/scripts/websearch/owui_e2e_gate.py")
gate = importlib.util.module_from_spec(spec); spec.loader.exec_module(gate)
MODEL = sys.argv[1]; LOG = "$STACK_REPO/logs/mlx_vlm.log"
api = gate.login("http://localhost:3000", os.environ.get("OWUI_ADMIN_EMAIL", "admin@a.a"), os.environ.get("OWUI_ADMIN_PASSWORD", "admin"))
log_off = os.path.getsize(LOG)
qs = ["Remember the number 4471. Think briefly, then reply with one short sentence.",
      "Now remember the colour green. One short sentence.",
      "What number and colour did I ask you to remember? One line."]
chat, uid, aid = gate.chat_payload(MODEL, qs[0], "c105 echo check")
chat_id = api.post("/api/v1/chats/new", {"chat": chat})["id"]
session_id = str(uuid.uuid4()); messages = []
def wait_done(aid):
    for _ in range(240):
        doc = api.get(f"/api/v1/chats/{chat_id}"); msg = gate.assistant_message(doc, aid)
        if msg.get("done"): return msg
        time.sleep(1)
    raise SystemExit("assistant message never done")
for i, q in enumerate(qs):
    if i > 0:
        uid, aid = str(uuid.uuid4()), str(uuid.uuid4())
        # persist the new turn the way the frontend does (history + messages), then complete
        doc = api.get(f"/api/v1/chats/{chat_id}")["chat"]
        prev_aid = doc["history"]["currentId"]; ts = int(time.time())
        um = {"id": uid, "parentId": prev_aid, "childrenIds": [aid], "role": "user", "content": q, "timestamp": ts, "models": [MODEL]}
        am = {"id": aid, "parentId": uid, "childrenIds": [], "role": "assistant", "content": "", "model": MODEL, "modelName": MODEL, "modelIdx": 0, "timestamp": ts, "done": False}
        doc["history"]["messages"][prev_aid]["childrenIds"] = [uid]
        doc["history"]["messages"].update({uid: um, aid: am}); doc["history"]["currentId"] = aid
        doc["messages"] = doc["messages"] + [um, am]
        api.post(f"/api/v1/chats/{chat_id}", {"chat": doc})
    messages.append({"role": "user", "content": q})
    payload = gate.completion_payload(MODEL, q, chat_id, aid, session_id)
    payload["messages"] = list(messages); payload["features"] = {"web_search": False, "code_interpreter": False, "image_generation": False, "memory": False}
    api.post("/api/chat/completions", payload, timeout=600)
    msg = wait_done(aid)
    content = msg.get("content") or ""
    print(f"turn {i+1}: persisted assistant content ({len(content)} chars): {content[:160]!r}")
    # echo EXACTLY the persisted content, as the frontend does
    messages.append({"role": "assistant", "content": content})
time.sleep(1)
new = open(LOG).read()[log_off:]
for l in new.splitlines():
    if chat_id[:8] in l or "Prompt-end retention" in l or "rewind" in l.lower():
        m = re.search(r"session=(\S+) cached_tokens=(\d+) prompt_tokens=(\d+)", l)
        if m and chat_id[:8] in m.group(1): print("REQ ", l[:19], m.group(0))
        elif "Prompt-end retention" in l or "rewind" in l.lower(): print("LOG ", l[:19], l.split(" - ")[-1][:150])
print("chat_id", chat_id)
