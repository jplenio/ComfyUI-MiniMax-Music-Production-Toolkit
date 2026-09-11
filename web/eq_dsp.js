// Independent response preview. Backend validates/rendering remains authoritative.
// Mathematical reference: https://www.w3.org/TR/audio-eq-cookbook/
export const TYPES = ["peak", "low_shelf", "high_shelf", "highpass", "lowpass", "notch"];
export function coefficients(band, sr) {
    const w = 2 * Math.PI * band.frequency_hz / sr, c = Math.cos(w), s = Math.sin(w);
    const a = 10 ** ((band.gain_db ?? 0) / 40), q = band.q ?? Math.SQRT1_2;
    let alpha = s / (2*q), den = [1+alpha, -2*c, 1-alpha], num;
    switch (band.type) {
        case "peak": num = [1+alpha*a, -2*c, 1-alpha*a]; den = [1+alpha/a, -2*c, 1-alpha/a]; break;
        case "lowpass": num = [(1-c)/2, 1-c, (1-c)/2]; break;
        case "highpass": num = [(1+c)/2, -(1+c), (1+c)/2]; break;
        case "notch": num = [1, -2*c, 1]; break;
        case "low_shelf": case "high_shelf": {
            alpha = s/2 * Math.sqrt((a+1/a)*(1/(band.slope ?? 1)-1)+2);
            const v = 2*Math.sqrt(a)*alpha;
            if (band.type === "low_shelf") {
                num = [a*((a+1)-(a-1)*c+v), 2*a*((a-1)-(a+1)*c), a*((a+1)-(a-1)*c-v)];
                den = [(a+1)+(a-1)*c+v, -2*((a-1)+(a+1)*c), (a+1)+(a-1)*c-v];
            } else {
                num = [a*((a+1)+(a-1)*c+v), -2*a*((a-1)+(a+1)*c), a*((a+1)+(a-1)*c-v)];
                den = [(a+1)-(a-1)*c+v, 2*((a-1)-(a+1)*c), (a+1)-(a-1)*c-v];
            }
            break;
        }
        default: throw new Error("Unknown filter type");
    }
    return [...num, ...den].map(v => v/den[0]);
}
export function response(settings, sr, frequencies) {
    const rows = settings.bands.filter(b => b.enabled !== false).map(b => coefficients(b, sr));
    return frequencies.map(f => {
        const w = 2*Math.PI*f/sr;
        let gain = settings.preamp_db ?? 0;
        for (const row of rows) {
            const power = offset => (row[offset]+row[offset+1]*Math.cos(w)+row[offset+2]*Math.cos(2*w))**2
                + (row[offset+1]*Math.sin(w)+row[offset+2]*Math.sin(2*w))**2;
            gain += 10*Math.log10(Math.max(power(0), 1e-30)/Math.max(power(3), 1e-30));
        }
        return gain;
    });
}
export function readSettings(text) {
    const value = JSON.parse(text);
    if (value.schema !== "minimax_eq_v1" || !Array.isArray(value.bands) || value.bands.length > 8)
        throw new Error("Editor needs minimax_eq_v1 (batch proposals render after execution)");
    return structuredClone(value);
}
