from urllib.parse import urlparse, parse_qs
from js import window, document, alert, Object
import json

def getargs():
	parsed=urlparse(window.location.href)
	site=parsed.netloc
	return parse_qs(parsed.query)


def getvid(url):
	parsed=urlparse(url)
	site=parsed.netloc
	return parse_qs(parsed.query)['list'][0]



# -------------------------------------------------------------
# 1. BUILD THE UI ENTIRELY IN PYTHON
# -------------------------------------------------------------
body = document.body
body.style.fontFamily = "sans-serif"
body.style.maxWidth = "500px"
body.style.margin = "40px auto"
body.style.padding = "0 20px"

def addvid(div_read,VID="NB6lnoyvX1k"):
    output_el = document.createElement("iframe")
    print(VID)
    output_el.src = f"https://www.youtube.com/embed/{VID}"#"https://www.youtube.com/embed/zuJV-DAv_wE?rel=0&amp;controls=1&amp;autoplay=1&amp;mute=1&amp;start=0"
    print(output_el.src)
    output_el.style = "position:absolute;left:0;top:0;width:100%;height:100%;pointer-events:auto"
    output_el.allow = "autoplay; encrypted-media"
    output_el.allowfullscreen = ""
    output_el.title = "VIDEO TITLE"
    div_read.appendChild(output_el)
def append_vid(body,VID="NB6lnoyvX1k"):
    div_read = document.createElement("div")
    addvid(div_read,VID)
    body.appendChild(div_read)


def addlist(div_read,VID="NB6lnoyvX1k"):
    output_el = document.createElement("iframe")
    print(VID)
    output_el.src = f"https://www.youtube.com/embed/videoseries?list={VID}"#"https://www.youtube.com/embed/zuJV-DAv_wE?rel=0&amp;controls=1&amp;autoplay=1&amp;mute=1&amp;start=0"
    print(output_el.src)
    output_el.style = "position:absolute;left:0;top:0;width:100%;height:100%;pointer-events:auto"
    output_el.allow = "autoplay; encrypted-media"
    output_el.allowfullscreen = ""
    output_el.title = "VIDEO TITLE"
    div_read.appendChild(output_el)
def append_list(body,VID="NB6lnoyvX1k"):
    div_read = document.createElement("div")
    addvid(div_read,VID)
    body.appendChild(div_read)




if 'v' in list(getargs().keys()):
	VID=getargs()['v'][0]
	append_vid(body,VID)
elif 'list' in list(getargs().keys()):
	VID=getargs()['list'][0]
	append_list(body,VID)
else:
	print("no video specifyed")
	append_vid(body,"L6oOluDPGnI")
