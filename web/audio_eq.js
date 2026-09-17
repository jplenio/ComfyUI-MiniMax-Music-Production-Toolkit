import { app } from "../../scripts/app.js";
import { response, TYPES, readSettings } from "./eq_dsp.js";
import { presetControl } from "./eq_presets.js";
import { applyTooltip } from "./prompt_ui_utils.js";

// Canonical value is the existing STRING widget, not an extra serialized UI value.
export function attachEQEditor(node) {
    const widget = node.widgets?.find(w => w.name === "eq_settings_json");
    if (!widget || !node.addDOMWidget || node.__miniMaxEQEditor) return;
    node.__miniMaxEQEditor = true;
    const root = document.createElement("div");
    root.style.cssText = "font:12px sans-serif;color:#eee;background:#20232a;padding:8px;box-sizing:border-box;width:100%;overflow:auto";
    const canvas = document.createElement("canvas");
    canvas.style.cssText = "width:100%;height:210px;touch-action:none";
    canvas.setAttribute("aria-label", "EQ frequency response. Use the numeric band controls below for keyboard editing.");
    const status = document.createElement("div"), controls = document.createElement("div"), rows = document.createElement("div");
    status.setAttribute("role", "status");
    root.append(canvas, status, controls, rows);
    let settings, sr = 48000, selected = 0, last = null, lastLinked = null, measured = null, dragging = false;
    const undo = [];
    const linked = () => node.inputs?.some(i => i.name === "eq_settings_json" && i.link != null);
    const dirty = () => node.setDirtyCanvas?.(true, true);
    const remember = () => { undo.push(String(widget.value)); if (undo.length > 40) undo.shift(); };
    const presets = presetControl("Manual EQ preset", "manual", () => settings, linked, value => {
        settings = value; selected = 0; commit(); renderRows();
    });
    root.prepend(presets.root);
    function commit(record = true) {
        if (linked()) return;
        if (record) remember();
        widget.value = JSON.stringify(settings);
        last = widget.value;
        widget.callback?.(widget.value);
        measured = null;
        presets.sync();
        dirty();
        draw();
    }
    function button(label, tooltip, action) {
        const el = document.createElement("button"); el.textContent = label;
        el.type = "button"; el.style.margin = "3px"; el.onclick = action; controls.append(el);
        applyTooltip(el, tooltip);
        return el;
    }
    button("Add band", "Adds one peak band at 1 kHz with 0 dB gain, up to the eight-band limit. Linked settings (auto-EQ connected) cannot be edited.", () => {
        if (!settings || linked() || settings.bands.length >= 8) return;
        remember();
        settings.bands.push({id: `band-${globalThis.crypto?.randomUUID?.() ?? Date.now()}`, enabled:true,
            type:"peak", frequency_hz:1000, gain_db:0, q:1, slope:1});
        selected = settings.bands.length-1; commit(false); renderRows();
    });
    button("Reset", "Clears every band and the preamp back to a flat curve. Undo brings the previous setting back.", () => {
        if (linked()) return;
        remember(); settings = {schema:"minimax_eq_v1", preamp_db:0, bands:[]}; commit(false); renderRows();
    });
    button("Undo", "Restores the last edit you made in this editor. The list is cleared when you reset or connect linked settings.", () => {
        if (linked() || !undo.length) return;
        widget.value = undo.pop(); last = null; sync(); widget.callback?.(widget.value); dirty();
    });
    function numeric(parent, label, value, min, max, step, change) {
        const wrap = document.createElement("label"); wrap.textContent = label+" ";
        const input = document.createElement("input"); input.type = "number";
        Object.assign(input, {value, min, max, step, disabled: linked()});
        input.style.width = "72px"; input.setAttribute("aria-label", label);
        input.onchange = () => {
            const number = Number(input.value);
            if (!Number.isFinite(number) || number < min || number > max) { input.value = value; return; }
            remember(); change(number); commit(false);
        };
        wrap.append(input); parent.append(wrap);
    }
    function renderRows() {
        rows.replaceChildren();
        if (!settings) return;
        numeric(rows, "Preamp dB", settings.preamp_db ?? 0, -24, 24, 0.1, v => settings.preamp_db=v);
        settings.bands.forEach((b, i) => {
            const row = document.createElement("div");
            row.style.cssText = "display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-top:6px;border-top:1px solid #555;padding-top:5px";
            const enabled = document.createElement("input"); enabled.type="checkbox";
            enabled.checked=b.enabled!==false; enabled.disabled=linked(); enabled.setAttribute("aria-label", `Band ${i+1} enabled`);
            enabled.onchange=()=>{remember(); b.enabled=enabled.checked; commit(false);};
            const label = document.createElement("span"); label.textContent=`${i+1}`;
            const kind = document.createElement("select"); kind.setAttribute("aria-label", `Band ${i+1} type`);
            TYPES.forEach(type=>{const option=document.createElement("option"); option.value=type; option.textContent=type.replaceAll("_", " ");kind.append(option);});
            kind.value=b.type; kind.disabled=linked();
            kind.onchange=()=>{remember();b.type=kind.value;commit(false);renderRows();};
            row.append(label, enabled, kind);
            numeric(row, "Hz", b.frequency_hz, 20, Math.min(20000,sr*0.45), 1, v=>b.frequency_hz=v);
            if (["peak","low_shelf","high_shelf"].includes(b.type))
                numeric(row, "dB", b.gain_db??0, -12,12,0.1,v=>b.gain_db=v);
            if (b.type.includes("shelf")) numeric(row,"Slope",b.slope??1,0.25,1,0.05,v=>b.slope=v);
            else numeric(row,"Q",b.q??Math.SQRT1_2,0.2,10,0.05,v=>b.q=v);
            const remove=document.createElement("button");remove.textContent="Remove";remove.disabled=linked();
            applyTooltip(remove, "Removes this band from the curve. Linked settings (auto-EQ connected) are read-only.");
            remove.onclick=()=>{remember();settings.bands.splice(i,1);commit(false);renderRows();};row.append(remove);
            row.onfocusin=()=>{selected=i;draw();}; rows.append(row);
        });
    }
    function draw() {
        const width=Math.max(260,canvas.clientWidth||500),height=210,dpr=globalThis.devicePixelRatio||1;
        canvas.width=width*dpr;canvas.height=height*dpr;
        const ctx=canvas.getContext("2d");if(!ctx)return;ctx.scale(dpr,dpr);
        const maxHz=Math.min(20000,sr*0.45),fx=f=>32+(width-44)*Math.log(f/20)/Math.log(maxHz/20),gy=g=>height/2-g*5;
        ctx.fillStyle="#171a20";ctx.fillRect(0,0,width,height);ctx.font="10px sans-serif";
        for(const d of [-18,-12,-6,0,6,12,18]){ctx.strokeStyle=d===0?"#777":"#343a44";ctx.beginPath();ctx.moveTo(30,gy(d));ctx.lineTo(width,gy(d));ctx.stroke();ctx.fillStyle="#bbb";ctx.fillText(String(d),2,gy(d)+3);}
        for(const f of [20,100,1000,10000]){if(f>maxHz)continue;ctx.fillStyle="#bbb";ctx.fillText(f>=1000?`${f/1000}k`:String(f),fx(f),height-3);}
        if(!settings)return;
        try {
            const freq=Array.from({length:256},(_,i)=>20*(maxHz/20)**(i/255));
            const plot=(frequencies,gains,color,lineWidth)=>{ctx.strokeStyle=color;ctx.lineWidth=lineWidth;ctx.beginPath();frequencies.forEach((f,i)=>{const x=fx(f),y=gy(Math.max(-20,Math.min(20,gains[i])));i?ctx.lineTo(x,y):ctx.moveTo(x,y);});ctx.stroke();};
            settings.bands.forEach((b,i)=>{if(b.enabled!==false)plot(freq,response({bands:[b],preamp_db:0},sr,freq),i===selected?"#a5a9ff":"#555c75",1);});
            plot(freq,response(settings,sr,freq),"#62ddd0",2);
            if(measured)plot(measured.frequency_hz,measured.response_db,"#ffca78",1);
            settings.bands.forEach((b,i)=>{ctx.fillStyle=b.enabled===false?"#777":"#fff";ctx.beginPath();ctx.arc(fx(b.frequency_hz),gy(b.gain_db??0),i===selected?6:4,0,Math.PI*2);ctx.fill();ctx.fillText(String(i+1),fx(b.frequency_hz)+8,gy(b.gain_db??0)-4);});
        } catch(error){status.textContent=error.message;}
    }
    function sync() {
        if(last===widget.value && lastLinked===Boolean(linked()))return;
        last=widget.value;
        lastLinked=Boolean(linked());
        try { settings=linked() && measured ? measured.settings : readSettings(widget.value); status.textContent=linked()?"Connected settings: read-only. Gold = last rendered curve.":`Preview at ${sr} Hz; actual rate updates after execution. Not realtime audio.`; }
        catch(error){settings=null;status.textContent=error.message;}
        presets.sync();renderRows();draw();
    }
    canvas.onpointerdown=event=>{
        if(!settings?.bands.length||linked())return;
        const rect=canvas.getBoundingClientRect(), x=event.clientX-rect.left;
        const hz=20*(Math.min(20000,sr*0.45)/20)**((x-32)/(rect.width-44));
        selected=settings.bands.reduce((best,b,i)=>Math.abs(Math.log(b.frequency_hz/hz))<Math.abs(Math.log(settings.bands[best].frequency_hz/hz))?i:best,0);
        remember();dragging=true;canvas.setPointerCapture(event.pointerId);
    };
    canvas.onpointermove=event=>{
        if(!dragging||linked())return;
        const rect=canvas.getBoundingClientRect(),b=settings.bands[selected],maxHz=Math.min(20000,sr*0.45);
        b.frequency_hz=Math.round(Math.max(20,Math.min(maxHz,20*(maxHz/20)**((event.clientX-rect.left-32)/(rect.width-44)))));
        if(["peak","low_shelf","high_shelf"].includes(b.type))b.gain_db=Math.round(Math.max(-12,Math.min(12,(105-(event.clientY-rect.top))/5))*10)/10;
        commit(false);
    };
    canvas.onpointerup=()=>{dragging=false;renderRows();};canvas.onpointercancel=()=>{dragging=false;renderRows();};
    const dom=node.addDOMWidget("eq_editor","minimax_eq_editor",root,{serialize:false,hideOnZoom:false});
    dom.computeSize=width=>[width,430];
    const originalDraw=node.onDrawForeground, originalExecuted=node.onExecuted, originalRemoved=node.onRemoved;
    node.onDrawForeground=function(...args){originalDraw?.apply(this,args);sync();};
    node.onExecuted=function(output){originalExecuted?.apply(this,arguments);try{const rep=JSON.parse(output.eq_report?.[0]);sr=rep.sample_rate;measured=rep.batch_reports?.[0];if(linked()&&measured){settings=measured.settings;status.textContent="Connected EQ: showing rendered batch item 1 (read-only).";}renderRows();draw();}catch{/* other execution output */}};
    const resize=new ResizeObserver(draw);resize.observe(canvas);
    node.onRemoved=function(...args){resize.disconnect();root.remove();originalRemoved?.apply(this,args);};
    sync();return {root,sync};
}

app.registerExtension({name:"minimax_music_production_toolkit.parametricEQ",
    nodeCreated(node){if(node.comfyClass==="MiniMaxParametricEQ")attachEQEditor(node);},
});
