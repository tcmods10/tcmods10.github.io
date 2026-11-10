from js import window, document, alert, Object
import json


def getvid(url):
	from urllib.parse import urlparse, parse_qs
	parsed=urlparse(url)
	site=parsed.netloc
	if site in ["youtube.com","www.youtube.com","music.youtube.com"]:
		return parse_qs(parsed.query)['v'][0]
	elif site=="youtu.be":
		return parsed.path[1:]



# -------------------------------------------------------------
# 1. BUILD THE UI ENTIRELY IN PYTHON
# -------------------------------------------------------------
body = document.body
body.style.fontFamily = "sans-serif"
body.style.maxWidth = "500px"
body.style.margin = "40px auto"
body.style.padding = "0 20px"

# Title
title = document.createElement("h2")
title.textContent = "Supabase + PyScript (Python UI)"
body.appendChild(title)

# Input container
div_write = document.createElement("div")
label = document.createElement("label")
label.innerHTML = "<strong>YOUTUBE VIDEO EMBEDDED PLAYER AND URL PARSER"
div_write.appendChild(label)

input_el = document.createElement("input")
input_el.id = "testData"
input_el.placeholder = "youtube video url"
input_el.style.width = "70%"
input_el.style.padding = "8px"
div_write.appendChild(input_el)

insert_btn = document.createElement("button")
insert_btn.textContent = "PLAY"
insert_btn.style.padding = "8px 12px"
insert_btn.style.marginLeft = "10px"
div_write.appendChild(insert_btn)

body.appendChild(div_write)

# Divider
body.appendChild(document.createElement("hr"))

def addvid(div_read,VID="NB6lnoyvX1k"):
    output_el = document.createElement("iframe")
    print(VID)
    output_el.src = f"https://www.youtube.com/embed/{VID}?si={VID}"#"https://www.youtube.com/embed/zuJV-DAv_wE?rel=0&amp;controls=1&amp;autoplay=1&amp;mute=1&amp;start=0"
    print(output_el.src)
    output_el.style = "position:absolute;left:0;top:0;width:100%;height:100%;pointer-events:auto"
    output_el.allow = "autoplay; encrypted-media"
    output_el.allowfullscreen = ""
    output_el.title = "VIDEO TITLE"
    div_read.appendChild(output_el)
# Read container
def append_vid(body,VID="NB6lnoyvX1k"):
    div_read = document.createElement("div")
    addvid(div_read,VID)
    body.appendChild(div_read)

#def btn(event):
#    VID=input_el.value.strip()
#    append_vid(body,VID)#="svFHMJPg2UA")
def btn(event):
    VID=getvid(input_el.value.strip())
    append_vid(body,VID)#="svFHMJPg2UA")



insert_btn.onclick=btn

