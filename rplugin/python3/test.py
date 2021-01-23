
from airlatex import AirLatex, AirLatexSession, SideBar


# for debugging, start nvim with
# NVIM_LISTEN_ADDRESS=/tmp/nvim nvim
if __name__ == "__main__":
    import asyncio
    import os
    from pynvim import attach
    DOMAIN = os.environ["DOMAIN"]
    nvim = attach('socket', path='/tmp/nvim')
    airlatex = AirLatex(nvim)
    servername = nvim.eval("v:servername")
    airlatex.openSidebar()

    session = AirLatexSession(DOMAIN, servername, airlatex.sidebar)
    session.login(nvim)

    # async def main():
    #     sl = AirLatexSession(DOMAIN, None, sidebar)
    #     sl.login(nvim)
    #     project = sl.projectList()[1]
    #     print(">>>>",project)
    #     sl.connectProject(nvim, project)
    #     time.sleep(3)
    #     # print(">>>",project)
    #     doc = project["rootFolder"][0]["docs"][0]
    #     project["handler"].joinDocument(doc)
    #     time.sleep(6)
    #     print(">>>> sending ops")
    #     # project["handler"].sendOps(doc, [{'p': 0, 'i': '0abB\n'}])
    #     # project["handler"].sendOps(doc, [{'p': 0, 'i': 'def\n'}])
    #     # project["handler"].sendOps(doc, [{'p': 0, 'i': 'def\n'}])
#
    # asyncio.run(main())
