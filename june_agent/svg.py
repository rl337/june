
class SVGObject(object):

    def __init__(self, tag, id, style=None, self_closing=False, children=None, attributes=None):
        self.tag = tag
        self.attributes = { 'id': id, 'style': style }
        self.attribute_order = ["id", "style"]
        self.self_closing = self_closing
        self.children = children

        if attributes is not None:
            for k in attributes:
                self.attributes[k] = attributes[k]

    def get_id(self):
        return self.attributes.get('id', None)

    def render(self, level=0):
        rendered_children = []
        if self.children is not None:
            rendered_children = [ child.render(level + 1) for child in self.children ]

        attributes_str = ""
        if self.attributes is not None:
            rendered_attributes = []

            attribute_order = [ ]
            if self.attribute_order is not None:
                attribute_order += self.attribute_order
            attribute_order += [ x for x in self.attributes.keys() if x not in attribute_order ]

            for attribute in attribute_order:
                value = self.attributes[attribute]
                if value is None:
                    continue
                if isinstance(value, list):
                    for v in value:
                        rendered_attributes.append('{0}="{1}"'.format(attribute, v))
                else:
                    rendered_attributes.append('{0}="{1}"'.format(attribute, value))

            if len(rendered_attributes) > 0:
                attributes_str = " {0}".format(" ".join(rendered_attributes))

        indent = " " * level
        if len(rendered_children) > 0:
            return "{3}<{0}{2}>\n{1}\n{3}</{0}>\n".format(
                self.tag,
                "\n".join(rendered_children),
                attributes_str,
                indent
            )
        else:
            if self.self_closing:
                return "{2}<{0}{1} />".format(self.tag, attributes_str, indent)
            else:
                return "{2}<{0}{1}></{0}>".format(self.tag, attributes_str, indent)

    def __str__(self):
        return self.render(0)


class Style(object):
    def __init__(self, stroke="black", fill="black", stroke_width=1, stroke_opacity=1, fill_opacity=1, font=None):
        self.attributes = {
            "stroke": stroke,
            "fill": fill,
            "stroke-width": stroke_width,
            "stroke-opacity": stroke_opacity,
            "fill-opacity": fill_opacity
        }

        if font is not None:
            self.attributes['font'] = font

    def __str__(self):
        return "; ".join([
            "{0}:{1}".format(x, self.attributes[x])
            for x in self.attributes
            if self.attributes[x] is not None
        ])

class Font(object):

    def __init__(self, face=None, decoration=None, size=None):
        self.face = face
        self.decoration = decoration
        self.size = size

    def __str__(self):
        parts = []
        if self.decoration is not None:
            parts.append(self.decoration)
        if self.face is not None:
            parts.append(self.face)
        if self.size is not None:
            parts.append(self.size)

        if len(parts) < 1:
            return ""

        return " ".join(parts)


class SansSerif(Font):

    def __init__(self, size, decoration=None):
        super(SansSerif, self).__init__('sans-serif', decoration, size)


class SVG(SVGObject):

    def __init__(self, id, width, height, children=None):
        super(SVG, self).__init__("svg", id, None, False, children, {
            "width": width,
            "height": height,
            "xmlns": ["http://www.w3.org/2000/svg"]
        })

        self.attribute_order = ["xmlns"] + self.attribute_order

    def get_width(self):
        return self.attributes.get('width', None)

    def get_height(self):
        return self.attributes.get('height', None)


class Rectangle(SVGObject):

    def __init__(self, id, x, y, width, height, style=None):
         super(Rectangle, self).__init__("rect", id, style, True, None, {
             "x": x,
             "y": y,
            "width": width,
            "height": height
         })
         self.attribute_order += ["x", "y", "width", "height"]

    def get_width(self):
        return self.attributes.get('width', None)

    def get_height(self):
        return self.attributes.get('height', None)

    def get_x(self):
        return self.attributes.get('x', None)

    def get_y(self):
        return self.attributes.get('y', None)

class Line(SVGObject):

    def __init__(self, id, x1, y1, x2, y2, style):
        super(Line, self).__init__("path", id, style, True, None, {
            "d": "m {0},{1} {2},{3}".format(x1, y1, x2, y2)
        })

        self.attribute_order = ["d"] + self.attribute_order


class Text(SVGObject):

    def __init__(self, id, x, y, text, style):
        super(Text, self).__init__("text", id, style, False, { RawText(text) }, {
            'x': x,
            'y': y
        })
        self.attribute_order = ['x', 'y']

class RawText(object):
    def __init__(self, text):
        self.text = text

    def render(self, level=0):
        if self.text is None:
            return ""

        lines = self.text.strip().split("\n")
        result = lines[0]
        rest = lines[1:]

        indent = ' ' * level
        for line in rest:
            result = "{0}{1}\n".format(indent, line)

        return result

    def __str__(self):
        return self.render(0)
