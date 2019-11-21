# pythonx/foo_wrap.py
from airlatex import AirLatex as _AirLatex
import vim, time

al = _AirLatex(vim)

def openSidebar():
    return al.openSidebar()

def sidebarRefresh():
    return al.sidebarRefresh(None)

def sidebarStatus():
    return al.sidebarStatus(None)

def projectEnter():
    return al.projectEnter(None)

def projectLeave():
    return al.projectLeave(None)

def sidebarClose():
    return al.sidebarClose(None)

def writeBuffer():
    return al.writeBuffer(None)
