shader_type canvas_item;

// Flash CXFORMWITHALPHA "add" part for untextured vector geometry
// (Polygon2D / Line2D).  The multiply part is applied through CanvasItem
// modulate, which propagates to children, so here we only add.
uniform vec4 ct_add : source_color = vec4(0.0);

void fragment() {
	vec4 c = COLOR;
	c.rgb += ct_add.rgb * c.a;
	c.a = clamp(c.a + ct_add.a, 0.0, 1.0);
	COLOR = c;
}
