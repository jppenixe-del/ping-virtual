// Detetor de bola por IA (YOLOv5n treinado para a bola de tenis de mesa) com onnxruntime-web.
// BolaIA.deteta(fonte, x, y, w, h, lado) -> [{x, y, w, h, c}] em coordenadas da fonte (recorte redimensionado para lado x lado).
window.BolaIA = (() => {
  let sess = null, carregando = null;
  const cv = document.createElement("canvas"), cx = cv.getContext("2d", {willReadFrequently: true});
  function carrega(){
    if (sess) return Promise.resolve(sess);
    if (carregando) return carregando;
    carregando = (async () => {
      if (!window.ort){
        await new Promise((ok, ko) => { const s = document.createElement("script"); s.src = "ia/ort.wasm.min.js"; s.onload = ok; s.onerror = ko; document.head.appendChild(s); });
      }
      ort.env.wasm.wasmPaths = new URL("ia/", location.href).href;
      ort.env.wasm.numThreads = self.crossOriginIsolated ? Math.min(4, navigator.hardwareConcurrency || 2) : 1;
      sess = await ort.InferenceSession.create("ia/bola.onnx", {executionProviders: ["wasm"], graphOptimizationLevel: "all"});
      return sess;
    })();
    return carregando;
  }
  async function deteta(fonte, x, y, w, h, lado, confMin){
    await carrega();
    lado = lado || 640; confMin = confMin ?? 0.2;
    cv.width = lado; cv.height = lado;
    cx.fillStyle = "#727272"; cx.fillRect(0, 0, lado, lado);
    const k = Math.min(lado/w, lado/h), dw = w*k, dh = h*k;
    cx.drawImage(fonte, x, y, w, h, 0, 0, dw, dh);
    const d = cx.getImageData(0, 0, lado, lado).data, N = lado*lado, t = new Float32Array(3*N);
    for (let p = 0, j = 0; p < N; p++, j += 4){ t[p] = d[j]/255; t[N + p] = d[j+1]/255; t[2*N + p] = d[j+2]/255; }
    const out = await sess.run({[sess.inputNames[0]]: new ort.Tensor("float32", t, [1, 3, lado, lado])});
    const o = out[sess.outputNames[0]], v = o.data, n = o.dims[1], st = o.dims[2];
    let cs = [];
    for (let i = 0; i < n; i++){
      const b = i*st, c = v[b+4]*v[b+5]; if (c < confMin) continue;
      const bx = v[b]/k + x, by = v[b+1]/k + y; if (v[b] > dw || v[b+1] > dh) continue;
      cs.push({x: bx, y: by, w: v[b+2]/k, h: v[b+3]/k, c});
    }
    // supressao dos repetidos (a mesma bola vista por varias caixas)
    cs.sort((a, b) => b.c - a.c); const fica = [];
    cs.forEach(a => { if (!fica.some(b => Math.hypot(a.x - b.x, a.y - b.y) < Math.max(a.w, b.w, 4)*0.7)) fica.push(a); });
    return fica;
  }
  return {carrega, deteta, pronta: () => !!sess};
})();
