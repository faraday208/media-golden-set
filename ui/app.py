
import gradio as gr
import sys
import os
from pathlib import Path

# Add parent directory (project root) to path to allow importing from src
current_dir = Path(__file__).parent.resolve()
project_root = current_dir.parent
sys.path.append(str(project_root))

from src.universal_selector import run_selector

def run_gui(source, report, target, count, dist_close, dist_upper, dist_full, dist_face, dist_other, character, force):
    # Construct distribution string
    # Normalize inputs to 0-1 range to be safe? 
    # universal_selector handles parsing.
    # User will likely input percentages like 30, 30, 40.
    
    # We can create string like: "close-up:30,upper-body:30..."
    dist_map = []
    if dist_close > 0: dist_map.append(f"close-up:{dist_close}")
    if dist_upper > 0: dist_map.append(f"upper-body:{dist_upper}")
    if dist_full > 0: dist_map.append(f"full-body:{dist_full}")
    # Face is now separate constraint, removed from dist string
    if dist_other > 0: dist_map.append(f"other:{dist_other}")
    
    dist_str = ",".join(dist_map)
    
    # If explicitly empty, user might want everything evenly, but let's require input or default
    if not dist_str:
        return "Error: Please specify at least one distribution value > 0", ""
        
    # Calculate face target count from percentage
    target_count = int(count)
    face_percentage = float(dist_face)
    face_limit = int(target_count * (face_percentage / 100.0))
    
    try:
        success, msg, report_content = run_selector(
            source=source,
            report=report,
            target=target,
            count=target_count,
            dist_str=dist_str,
            character=character if character.strip() else None,
            force=force,
            face_target=face_limit # Pass calculated count
        )
        
        status = "✅ Success!" if success else "❌ Failed!"
        full_log = f"**Status**: {status}\n\n**Message**: {msg}"
        
        return full_log, report_content
        
    except Exception as e:
        return f"❌ Critical Error: {str(e)}", ""

with gr.Blocks(title="Golden Set Generator") as demo:
    gr.Markdown("# 🏆 Golden Set Generator")
    gr.Markdown("Select the highest quality assets for your dataset training.")

    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown("### 1. Source & Target")
            source_input = gr.Textbox(label="Source Directory", placeholder="/path/to/images", value="/data/Data/cleaned_images")
            report_input = gr.Textbox(label="Quality Report Path", placeholder="/path/to/report.json", value="/data/Data/quality_report.json")
            target_input = gr.Textbox(label="Target Directory", placeholder="/path/to/golden_set", value="/data/Data/golden_set")
            force_input = gr.Checkbox(label="Force Overwrite Target", value=False)
            
            gr.Markdown("### 2. Selection Criteria")
            count_input = gr.Number(label="Total Images to Select", value=100, precision=0)
            character_input = gr.Textbox(label="Target Character (Optional)", placeholder="e.g. Aria")
            
        with gr.Column(scale=1):
            gr.Markdown("### 3. Distribution (Weights/Percentages)")
            gr.Info("Enter values representing ratios or percentages. e.g. 30, 30, 40.")
            d_close = gr.Number(label="Close-up", value=30)
            d_upper = gr.Number(label="Upper-body", value=30)
            d_full = gr.Number(label="Full-body", value=40)
            d_face = gr.Number(label="Face Visible Target (Min %)", value=0)
            d_other = gr.Number(label="Other (Remaining)", value=0)
            
            run_btn = gr.Button("🚀 Generate Golden Set", variant="primary")
            
    gr.Markdown("---")
    
    with gr.Row():
        with gr.Column():
            status_output = gr.Markdown(label="Status")
        with gr.Column():
            report_output = gr.Markdown(label="Selection Report")

    run_btn.click(
        fn=run_gui,
        inputs=[source_input, report_input, target_input, count_input, d_close, d_upper, d_full, d_face, d_other, character_input, force_input],
        outputs=[status_output, report_output]
    )

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0")
