import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { widget, settings, signature, refresh, CONNECTION_FIELDS } from "./llm_provider_ui.js";

async function action(node, name, extra = {}) {
    const response = await api.fetchApi("/minimax_music_toolkit/llm/configure", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({...settings(node), action: name, ...extra}),
    });
    const result = await response.json();
    if (!response.ok || result.error) throw new Error(result.error || "Could not configure the LLM connection.");
    return result;
}

function choose(title, field, help, submit) {
    const dialog = document.createElement("dialog");
    Object.assign(dialog.style, {maxWidth: "560px", width: "85vw", padding: "24px", borderRadius: "12px", background: "#202833", color: "#edf2f7", border: "1px solid #566779"});
    const heading = document.createElement("h3"); heading.textContent = title;
    const description = document.createElement("p"); description.textContent = help;
    const error = document.createElement("p"); error.style.color = "#ffb7ad";
    field.style.width = "100%"; field.style.padding = "10px";
    const confirm = document.createElement("button"); confirm.textContent = "Apply";
    const cancel = document.createElement("button"); cancel.textContent = "Cancel";
    confirm.style.margin = "16px 12px 0 0";
    confirm.onclick = async () => {
        confirm.disabled = true;
        try { await submit(field.value); dialog.close(); }
        catch (exc) { error.textContent = exc.message; }
        finally { confirm.disabled = false; }
    };
    cancel.onclick = () => dialog.close();
    dialog.onclose = () => { field.value = ""; dialog.remove(); };
    dialog.append(heading, description, field, error, confirm, cancel);
    document.body.append(dialog); dialog.showModal(); field.focus();
}

const LABELS = {
    backend: "Run language model", local_provider: "Local app", cloud_provider: "Cloud provider",
    server_url: "API address (blank = default)", remote_model: "Model ID", api_key_env: "Key variable (optional)",
    remote_max_tokens: "Output token limit", request_timeout: "Request timeout (seconds)",
};
let catalogPromise;
function providerCatalog() {
    if (!catalogPromise) catalogPromise = api.fetchApi("/minimax_music_toolkit/llm/providers")
        .then(response => { if (!response.ok) throw new Error("Provider help unavailable. Restart ComfyUI after updating."); return response.json(); })
        .catch(error => { catalogPromise = null; throw error; });
    return catalogPromise;
}

app.registerExtension({
    name: "minimax_music_production_toolkit.llm_providers",
    nodeCreated(node) {
        if ((node.comfyClass || node.type) !== "MiniMaxLLMChat") return;
        for (const [name, label] of Object.entries(LABELS)) {
            const w = widget(node, name); if (w) w.label = label;
        }
        for (const name of CONNECTION_FIELDS) {
            const w = widget(node, name); if (!w) continue;
            const previous = w.callback;
            w.callback = function(...args) {
                previous?.apply(this, args);
                // Provider changes discard overrides from a different server.
                // Credentials remain in server RAM until explicitly cleared or restart.
                if (["backend", "local_provider", "cloud_provider"].includes(name)) {
                    for (const field of ["server_url", "remote_model", "api_key_env", "credential_id"]) {
                        const target = widget(node, field); if (target) target.value = "";
                    }
                }
                refresh(node);
            };
        }
        const button = (name, label, callback) => {
            const w = node.addWidget("button", name, null, callback, {serialize: false});
            w.label = label;
            return w;
        };
        button("llm_ui_advanced", "Show / hide advanced GGUF settings", () => { node._llmAdvanced = !node._llmAdvanced; refresh(node); });
        button("llm_ui_key", "Set API key…", () => {
            const before = signature(node);
            const input = document.createElement("input"); input.type = "password"; input.autocomplete = "off";
            choose("API key for this connection", input,
                "Stored only in ComfyUI memory until restart. The provider key is never included in your workflow. Cloud API usage may be billed by the provider.",
                async key => {
                    if (signature(node) !== before) throw new Error("Connection changed. Close this dialog and try again.");
                    const result = await action(node, "set_key", {key});
                    if (signature(node) !== before) return;
                    widget(node, "credential_id").value = result.credential_id;
                    node.setDirtyCanvas?.(true, true);
                });
        });
        button("llm_ui_clear", "Clear session key", async () => {
            const before = signature(node);
            try { await action(node, "clear_key"); if (signature(node) === before) widget(node, "credential_id").value = ""; }
            catch (error) { alert(error.message); }
        });
        const find = button("llm_ui_models", "Find models / test connection…", async () => {
            if (node._llmFinding) return;
            node._llmFinding = true;
            const before = signature(node);
            const previousModel = widget(node, "remote_model")?.value;
            find.label = "Connecting…"; node.setDirtyCanvas?.(true, true);
            try {
                const result = await action(node, "models");
                if (signature(node) !== before) return;
                const select = document.createElement("select");
                for (const id of result.models) {
                    const option = document.createElement("option"); option.value = id; option.textContent = id; select.append(option);
                }
                if (result.models.includes(previousModel)) select.value = previousModel;
                choose("Choose a text chat model", select,
                    "These IDs come from your server. Choose a text / instruct model, not an embedding, image or audio model. No generation request has been sent.",
                    async model => {
                        if (signature(node) !== before || widget(node, "remote_model").value !== previousModel) throw new Error("Connection or model changed. Close this dialog and search again.");
                        widget(node, "remote_model").value = model;
                        node.setDirtyCanvas?.(true, true);
                    });
            } catch (error) { if (signature(node) === before) alert(error.message + " You can also enter the model ID manually."); }
            finally { node._llmFinding = false; find.label = "Find models / test connection…"; node.setDirtyCanvas?.(true, true); }
        });
        button("llm_ui_help", "Connection setup / status…", async () => {
            try {
                const config = settings(node);
                const catalog = await providerCatalog();
                const local = config.backend === "Local app / server";
                const name = local ? config.local_provider : config.cloud_provider;
                const profile = (local ? catalog.local : catalog.cloud)[name];
                const base = config.server_url || profile?.[0] || "Enter the API base from your provider's console (including /v1).";
                const field = document.createElement("textarea"); field.readOnly = true; field.rows = 9;
                field.value = `Provider: ${name}\nAPI address: ${base}\nKey: ${config.credential_id ? "Session key selected (valid until ComfyUI restart)." : "No session key; environment variable if configured."}\nKey variable: ${config.api_key_env || (!config.server_url ? profile?.[2] : "") || "none"}\n\n${local ? "1. Start the app's API server and load a text/instruct model.\n2. Check the port above; it may differ in your installation." : "1. Get an API key from the provider's developer console.\n2. Cloud prompts are sent to the provider; API usage may be billed."}\n3. Set API key if needed, then Find models.\n4. Select a text model, or enter its model ID manually.`;
                choose("Connection setup", field, "The address is reached from the computer running ComfyUI. In Docker or on a remote host, localhost refers to that environment.", async () => {});
            } catch (error) { alert(error.message); }
        });
        queueMicrotask(() => refresh(node));
    },
    loadedGraphNode(node) {
        if ((node.comfyClass || node.type) === "MiniMaxLLMChat") queueMicrotask(() => refresh(node));
    },
});
