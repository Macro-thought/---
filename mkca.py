
import urllib.request, os, ssl, socket
p = os.path.join(os.environ["LOCALAPPDATA"], "Temp", "mozilla_ca.pem")
try:
    with urllib.request.urlopen("https://curl.se/ca/cacert.pem", timeout=30) as r:
        data = r.read()
    open(p, "wb").write(data)
    print("downloaded", len(data))
except Exception as e:
    print("download fail", type(e).__name__, e)

# 看 github.com 证书链的签发者
ctx = ssl.create_default_context()
with socket.create_connection(("github.com", 443), timeout=20) as s:
    with ctx.wrap_socket(s, server_hostname="github.com") as ss:
        cert = ss.getpeercert()
        print("issuer:", dict(x[0] for x in cert["issuer"]))
        print("subject:", dict(x[0] for x in cert["subject"]))
