#version 450
// W142: one triangle that covers the whole output; the fragment shader does the rest.
void main() {
  vec2 corner = vec2((gl_VertexIndex << 1) & 2, gl_VertexIndex & 2);
  gl_Position = vec4(corner * 2.0 - 1.0, 0.0, 1.0);
}
