if has('nvim')
    finish
endif

let s:airlatex = yarp#py3('airlatex_wrap')

" com -nargs=0 AirLatex call s:airlatex.request(<f-args>)
" com -nargs=0 AirLatex call s:airlatex.call('__str__')
" com -nargs=1 AirLatex call s:airlatex.call('bar', <f-args>)
" func! AirLatex_Bar()
"     return s:airlatex.call('openSidebar')
" endfunc
com -nargs=0 AirLatex call AirLatex_openSidebar()

func! AirLatex_openSidebar()
    return s:airlatex.call('openSidebar')
endfunc

func! AirLatex_SidebarRefresh()
    return s:airlatex.call('sidebarRefresh')
endfunc

func! AirLatex_SidebarUpdateStatus()
    return s:airlatex.call('sidebarStatus')
endfunc

func! AirLatex_ProjectEnter()
    return s:airlatex.call('projectEnter')
endfunc

func! AirLatex_ProjectLeave()
    return s:airlatex.call('projectLeave')
endfunc

func! AirLatex_Close()
    return s:airlatex.call('sidebarClose')
endfunc

func! AirLatex_WriteBuffer()
    return s:airlatex.call('writeBuffer')
endfunc
