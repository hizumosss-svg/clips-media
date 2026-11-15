"""Push due items from schedule.json to Buffer as scheduled TikTok posts.
modes: probe (print orgs/channels/schema), push (create posts for items not yet in buffer_sent.json)"""
import json, os, sys, urllib.request, datetime

API = "https://api.buffer.com"
TOKEN = os.environ["BUFFER_TOKEN"].strip()

def gql(query, variables=None):
    req = urllib.request.Request(API, data=json.dumps({"query": query, "variables": variables or {}}).encode(),
        headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json", "User-Agent": "clips-media"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return {"http_error": e.code, "body": e.read().decode()[:2000]}

def tiktok_channel():
    orgs = gql("{ account { organizations { id name } } }")
    print("orgs:", json.dumps(orgs)[:800])
    for o in orgs["data"]["account"]["organizations"]:
        ch = gql("query($o: OrganizationId!){ channels(input:{organizationId:$o}){ id name service isQueuePaused } }", {"o": o["id"]})
        print("channels:", json.dumps(ch)[:800])
        for c in ch.get("data", {}).get("channels", []):
            if c["service"].lower() == "tiktok" and c["name"] == os.environ.get("BUFFER_CHANNEL", "mikola.npc"):
                return c["id"]
    raise SystemExit("channel mikola.npc not found in Buffer")

mode = sys.argv[1]
if mode == "probe":
    print("channel:", tiktok_channel())
    t = gql('{ __type(name:"CreatePostInput"){ inputFields{ name type{ name kind ofType{ name kind ofType{name kind ofType{name}} } } } } }')
    print("CreatePostInput:", json.dumps(t)[:3000])
    for n in ["AssetsInput", "AssetInput", "VideoAssetInput", "PostAssetInput"]:
        print(n, json.dumps(gql('{ __type(name:"%s"){ inputFields{ name type{ name kind ofType{ name kind ofType{name}} } } } }' % n))[:1500])
    sys.exit(0)

# push
sched = json.load(open("schedule.json"))
sent_path = "buffer_sent.json"
sent = json.load(open(sent_path)) if os.path.exists(sent_path) else []
now = datetime.datetime.now(datetime.timezone.utc)
cid = tiktok_channel()
changed = False
for it in sched:
    key = it["at"] + "|" + it["file"]
    at = datetime.datetime.fromisoformat(it["at"])
    if key in sent or at <= now + datetime.timedelta(minutes=3) or it.get("buffer") is False:
        continue
    if os.environ.get("ONLY_DRAFT") and not it.get("draft"):
        continue
    url = "https://raw.githubusercontent.com/hizumosss-svg/clips-media/main/" + it["file"]
    q = """mutation($i: CreatePostInput!){ createPost(input:$i){
      ... on PostActionSuccess { post { id dueAt status } }
      ... on MutationError { message } } }"""
    inp = {"channelId": cid, "text": it["caption"], "schedulingType": "automatic", "mode": "customScheduled",
           "dueAt": at.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
           "needsApproval": False, "assets": [{"video": {"url": url}}]}
    if it.get("draft"): inp["saveToDraft"] = True
    r = gql(q, {"i": inp})
    print(key, "->", json.dumps(r)[:1500])
    post = (((r.get("data") or {}).get("createPost") or {}).get("post"))
    if post:
        sent.append(key); changed = True
json.dump(sent, open(sent_path, "w"), indent=1)
