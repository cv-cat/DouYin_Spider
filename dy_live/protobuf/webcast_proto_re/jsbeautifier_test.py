import os
import re
import sys

import jsbeautifier as jsb

file = sys.argv[1]
basename = os.path.basename(file)

opts = jsb.BeautifierOptions({
    "indent_size": 4,
    "indent_char": ' ',
    "preserve_newlines": True,
    "max_preserve_newlines": 1,
    "end_with_newline": True,
    "max_char": 32768,
    # ["collapse", "expand", "end-expand", "none", "preserve-inline"]
    "brace_style": 'collapse',
    "break_chained_methods": False,
    "space_in_paren": False,
    "keep_array_indentation": False,
})
with open(file, 'r', encoding='utf8') as f:
    text = f.read()

text = text.replace('),','),\n').replace('},','},\n')
text = text.replace(',(',',\n(').replace(',{',',\n{')
text, _ = re.subn(r'([\w\.]+=function\(\))', r'\n\1', text)
text = jsb.beautify(text, opts)

with open(f"formatted.{basename}", 'w', encoding='utf8') as f:
    f.write(text)
