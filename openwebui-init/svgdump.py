import sys
import base64
import urllib.request
'''
purlple = green
magenta = grass green
cyan = dark red
blue = yellow
black = white
teal is what is used now
#20A5DA is claude's orange (#B96949)
'''
def main():
    if len(sys.argv) < 2 or len(sys.argv) > 3:
        print("Usage: lucide_icon_url.py <icon-name> [color]")
        print("Example: lucide_icon_url.py sliders-horizontal '#4db8c8'")
        print("Example: lucide_icon_url.py sliders-horizontal cornflowerblue")
        sys.exit(1)

    icon_name = sys.argv[1]
    color = sys.argv[2] if len(sys.argv) == 3 else "#4db8c8"

    url = f"https://unpkg.com/lucide-static@latest/icons/{icon_name}.svg"

    try:
        with urllib.request.urlopen(url) as r:
            svg = r.read().decode()
    except Exception as e:
        print(f"Error fetching icon '{icon_name}': {e}")
        sys.exit(1)

    svg = svg.replace('stroke="currentColor"', f'stroke="{color}"')
    svg = svg.replace('stroke-width="2"', 'stroke-width="2.5"')

    encoded = base64.b64encode(svg.encode()).decode()
    print(f"self.icon= '''data:image/svg+xml;base64,{encoded}'''")

if __name__ == "__main__":
    main()
