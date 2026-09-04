import { app } from "../../scripts/app.js";

// MiniMaxPromptReport renders its Markdown report directly inside the node.
//
// ComfyUI only wires its Markdown-capable TEXT_PREVIEW widget to the built-in
// PreviewAny / SaveText nodes.  This extension attaches the same preview
// widgets to MiniMaxPromptReport, switches the preview to Markdown mode by
// default and hides the plain STRING output widget, so the node shows the
// report as formatted Markdown instead of raw text.  The markdown STRING
// output itself is unchanged and still available for downstream use.

const NODE_TYPE = "MiniMaxPromptReport";
const PLAIN_OUTPUT_NAME = "markdown";
const PREVIEW_MODE_NAME = "preview_mode";

app.registerExtension({
    name: "minimax_music_production_toolkit.promptReportPreview",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== NODE_TYPE) return;

        const previewApi = window.comfyAPI?.textPreviewWidgets;
        if (!previewApi?.addTextPreviewWidgets || !previewApi?.updateTextPreviewWidgets) {
            console.warn(
                "[MiniMax Music Production Toolkit] This ComfyUI frontend does not expose the Markdown text-preview API; the prompt report will show as plain text."
            );
            return;
        }

        const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            originalOnNodeCreated?.apply(this, arguments);
            try {
                // Hide the plain STRING output widget; the Markdown preview replaces it.
                const plain = this.widgets?.find((widget) => widget.name === PLAIN_OUTPUT_NAME);
                if (plain) {
                    plain.options.hidden = true;
                    plain.hidden = true;
                }
                previewApi.addTextPreviewWidgets(this);
                const toggle = this.widgets?.find((widget) => widget.name === PREVIEW_MODE_NAME);
                if (toggle) {
                    toggle.value = true; // Markdown mode by default
                    toggle.callback?.(true);
                }
                this.setDirtyCanvas?.(true, true);
            } catch (error) {
                console.warn(
                    "[MiniMax Music Production Toolkit] Could not enable the Markdown preview for MiniMaxPromptReport:",
                    error
                );
            }
        };

        const originalOnExecuted = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (output) {
            originalOnExecuted?.apply(this, arguments);
            try {
                previewApi.updateTextPreviewWidgets(this, output);
                const toggle = this.widgets?.find((widget) => widget.name === PREVIEW_MODE_NAME);
                if (toggle && toggle.value !== true) {
                    toggle.value = true;
                    toggle.callback?.(true);
                }
            } catch (error) {
                console.warn(
                    "[MiniMax Music Production Toolkit] Could not update the Markdown preview for MiniMaxPromptReport:",
                    error
                );
            }
        };
    },
});
