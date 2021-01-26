
from airlatex import AirLatex, AirLatexSession, SideBar, DocumentBuffer


# for debugging, start nvim with
# NVIM_LISTEN_ADDRESS=/tmp/nvim nvim
if __name__ == "__main__":
    import asyncio
    import os
    from pynvim import attach
    import time
    DOMAIN = os.environ["DOMAIN"]
    nvim = attach('socket', path='/tmp/nvim')
    airlatex = AirLatex(nvim)
    servername = nvim.eval("v:servername")
    airlatex.openSidebar()

    session = AirLatexSession(DOMAIN, servername, airlatex.sidebar, nvim, https=False)
    session.login()
    project = session.projectList()[0]
    print(">>>>",project)
    session.connectProject(nvim, project)
    time.sleep(2)
    doc = project["rootFolder"][0]["docs"][0]
    doc["handler"] = project["handler"]
    doc = DocumentBuffer([doc], nvim)
    project["handler"].joinDocument(doc)
    time.sleep(2)
    print(">>>> sending ops")
    project["handler"].sendOps(doc, [{'p': 0, 'i': '0abB\n'}])
    project["handler"].sendOps(doc, [{'p': 0, 'i': 'def\n'}])
    project["handler"].sendOps(doc, [{'p': 0, 'i': 'def\n'}])
