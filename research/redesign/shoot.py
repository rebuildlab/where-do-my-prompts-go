"""Screenshot key pages of the built site.

  /workspace/.venv-pw/bin/python research/redesign/shoot.py before|after|after_ops [--dark|--light] [page ...]
Serves public/ on a local port and saves <prefix>_<page>_<desktop|mobile>.png here.
"""
import sys, threading, functools, http.server, socketserver
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
prefix = sys.argv[1]
dark = "--dark" in sys.argv
light = "--light" in sys.argv  # ops theme: dark is the default, --light sets the saved theme
only = [a for a in sys.argv[2:] if not a.startswith("--")]
PAGES = {"home": "/", "tool": "/vendors/openai-api/", "tool2": "/vendors/deepseek/",
         "changelog": "/changelog/", "method": "/about/"}
SIZES = {"desktop": (1440, 900), "mobile": (390, 844)}

Handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT / "public"))
Handler.log_message = lambda *a: None
srv = socketserver.TCPServer(("127.0.0.1", 0), Handler)
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()

with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
    for sname, (w, h) in SIZES.items():
        ctx = b.new_context(viewport={"width": w, "height": h}, device_scale_factor=1 if sname == "desktop" else 2,
                            color_scheme="dark" if dark else "light")
        if light:
            ctx.add_init_script("try{localStorage.setItem('theme','light')}catch(e){}")
        pg = ctx.new_page()
        for name, path in PAGES.items():
            if only and name not in only:
                continue
            pg.goto(f"http://127.0.0.1:{port}{path}", wait_until="networkidle")
            fn = OUT / f"{prefix}_{name}_{sname}{'_dark' if dark else ''}{'_light' if light else ''}.png"
            pg.screenshot(path=str(fn), full_page=True)
            print(fn.name)
        ctx.close()
    b.close()
srv.shutdown()
