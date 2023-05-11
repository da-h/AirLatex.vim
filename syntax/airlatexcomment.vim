syn match AirLatexHead   "┌"
syn match AirLatexBar    "│"
syn match AirLatexTail   "└"
syn match AirLatexCross   "┴"
syn match AirLatexAlong  "─"
syn match AirLatexParagraph  "¶"
syn match AirLatexEnd  "┐"

syn match AirLatexTitle "\%1l.*"

syntax match AirLatexUser /\(¶\s*\)\@<=\([^│]\+\)\(│\)\@=/
syntax match AirLatexDate /\(│\s*\)\@<=\(\d\{2}\/\d\{2}\/\d\{2}\s*\d\{2}:\d\{2}\)\(\s*\)\@=/

syntax match AirLatexComment /^#.*/

syntax match AirLatexResolve /^resolve/
highlight AirLatexResolve ctermfg=darkgreen guifg=#008000

" Match and highlight the checks (✓✓) in light green
syntax match AirLatexChecks /✓✓/
highlight AirLatexChecks ctermfg=lightgreen guifg=#00ff00

hi def link AirLatexTitle Comment

hi def link AirLatexComment Comment
hi def link AirLatexParagraph Comment
hi def link AirLatexCross Comment
hi def link AirLatexAlong Comment
hi def link AirLatexTail Comment
hi def link AirLatexHead Comment
hi def link AirLatexEnd Comment
hi def link AirLatexBar Comment

hi AirLatexUser ctermfg=lightblue guifg=#7aa6da
hi AirLatexDate ctermfg=7

hi AirLatexComment ctermfg=8
hi AirLatexParagraph ctermfg=8
hi AirLatexAlong ctermfg=8
hi AirLatexCross ctermfg=8
hi AirLatexHead ctermfg=8
hi AirLatexTail ctermfg=8
hi AirLatexBar ctermfg=8
hi AirLatexEnd ctermfg=8
