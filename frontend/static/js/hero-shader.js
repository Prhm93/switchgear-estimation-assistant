/*
 * Home page hero: slowly drifting contour lines, drawn with WebGL (written by hand, no library).
 *
 * A smooth noise field is cut into level lines, blue and faint, with one level in red. The field drifts
 * with time and with the scroll. Only the lines are drawn; the page background shows through.
 *
 * Cheap on purpose: half resolution, device pixel ratio capped at 1.5, and no frames at all while the
 * tab is hidden or the hero is off screen. With reduced motion, without WebGL or if the shader fails,
 * nothing is changed and the static line art in the HTML stays.
 */
(function () {
  "use strict";
  var hero = document.querySelector(".hero");
  var art = hero && hero.querySelector(".hero__art");
  if (!art || !window.matchMedia || !("IntersectionObserver" in window)) return;
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

  var canvas = document.createElement("canvas");
  canvas.className = "hero__canvas";
  canvas.setAttribute("aria-hidden", "true");
  var gl = canvas.getContext("webgl", { alpha: true, antialias: false, premultipliedAlpha: true,
                                         powerPreference: "low-power" });
  if (!gl) return;

  var VERTEX = "attribute vec2 a_pos; void main() { gl_Position = vec4(a_pos, 0.0, 1.0); }";
  var FRAGMENT = [
    "precision mediump float;",
    "uniform vec2 u_res;",
    "uniform float u_time;",
    "uniform float u_scroll;",
    "float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }",
    "float noise(vec2 p) {",
    "  vec2 i = floor(p); vec2 f = fract(p); vec2 u = f * f * (3.0 - 2.0 * f);",
    "  return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), u.x),",
    "             mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), u.x), u.y);",
    "}",
    "float field(vec2 p) {",
    "  float v = 0.0; float a = 0.5;",
    "  for (int i = 0; i < 4; i++) { v += a * noise(p); p *= 2.03; a *= 0.5; }",
    "  return v;",
    "}",
    "float level(vec2 px) {",
    "  vec2 uv = px / u_res.y;",
    "  vec2 p = uv * 1.8 + vec2(u_time * 0.012, u_scroll * 0.0011 + u_time * 0.004);",
    "  return field(p) * 9.0 + uv.y * 1.5;",
    "}",
    "void main() {",
    "  float l = level(gl_FragCoord.xy);",
    "  vec2 g = vec2(level(gl_FragCoord.xy + vec2(1.0, 0.0)) - l, level(gl_FragCoord.xy + vec2(0.0, 1.0)) - l);",
    "  float px = abs(l - floor(l + 0.5)) / max(length(g), 1e-4);",  // distance to the nearest line in pixels
    "  float line = 1.0 - smoothstep(0.35, 1.1, px);",
    "  float red = step(abs(floor(l + 0.5) - 5.0), 0.1);",
    "  vec3 col = mix(vec3(0.110, 0.373, 0.820), vec3(0.890, 0.118, 0.141), red);",
    "  float side = mix(0.45, 1.0, smoothstep(0.15, 0.85, gl_FragCoord.x / u_res.x));",  // calmer under the text
    "  float a = line * mix(0.42, 0.55, red) * side;",
    "  gl_FragColor = vec4(col * a, a);",
    "}"
  ].join("\n");

  function compile(type, text) {
    var s = gl.createShader(type);
    gl.shaderSource(s, text);
    gl.compileShader(s);
    return gl.getShaderParameter(s, gl.COMPILE_STATUS) ? s : null;
  }
  var vs = compile(gl.VERTEX_SHADER, VERTEX);
  var fs = compile(gl.FRAGMENT_SHADER, FRAGMENT);
  if (!vs || !fs) return;
  var program = gl.createProgram();
  gl.attachShader(program, vs);
  gl.attachShader(program, fs);
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) return;
  gl.useProgram(program);

  // One triangle that covers the whole canvas.
  gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
  var pos = gl.getAttribLocation(program, "a_pos");
  gl.enableVertexAttribArray(pos);
  gl.vertexAttribPointer(pos, 2, gl.FLOAT, false, 0, 0);
  var uRes = gl.getUniformLocation(program, "u_res");
  var uTime = gl.getUniformLocation(program, "u_time");
  var uScroll = gl.getUniformLocation(program, "u_scroll");

  art.appendChild(canvas);
  hero.classList.add("has-shader");  // hides the static lines; only now that the shader works

  function resize() {
    var scale = Math.min(window.devicePixelRatio || 1, 1.5) * 0.5;  // half resolution
    canvas.width = Math.max(1, Math.round(hero.clientWidth * scale));
    canvas.height = Math.max(1, Math.round(hero.clientHeight * scale));
    gl.viewport(0, 0, canvas.width, canvas.height);
  }

  var frame = 0;
  var onScreen = true;
  var start = performance.now();

  function draw(now) {
    frame = 0;
    gl.uniform2f(uRes, canvas.width, canvas.height);
    gl.uniform1f(uTime, (now - start) / 1000);
    gl.uniform1f(uScroll, window.scrollY || 0);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    run();
  }
  function run() {
    if (!frame && onScreen && !document.hidden) frame = window.requestAnimationFrame(draw);
  }
  function stop() {
    if (frame) window.cancelAnimationFrame(frame);
    frame = 0;
  }

  document.addEventListener("visibilitychange", function () {
    if (document.hidden) stop(); else run();
  });
  new IntersectionObserver(function (entries) {
    onScreen = entries[0].isIntersecting;
    if (onScreen) run(); else stop();
  }).observe(hero);
  window.addEventListener("resize", resize);
  canvas.addEventListener("webglcontextlost", function (event) {  // back to the static art
    event.preventDefault();
    stop();
    onScreen = false;
    hero.classList.remove("has-shader");
    canvas.remove();
  });

  resize();
  run();
})();
