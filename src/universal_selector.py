import argparse
import json
import os
import shutil
import sys
from collections import defaultdict
from pathlib import Path

def parse_distribution(dist_str):
    """Parses distribution string like 'close-up:30,upper-body:30,full-body:40'."""
    try:
        dist = {}
        parts = dist_str.split(',')
        for part in parts:
            key, val = part.split(':')
            dist[key.strip()] = float(val)
        
        # Normalize if sum is > 1 (assuming percentage if > 1, else ratio)
        total = sum(dist.values())
        if total > 1.01: # allow slight float error, basically if sum is significantly > 1 assume it's like 30, 30, 40
             for k in dist:
                 dist[k] /= total
                 
        return dist
    except Exception as e:
        print(f"Error parsing distribution string: {e}")
        sys.exit(1)

def load_data(source_dir, report_path):
    """Loads quality report and maps images to their data."""
    print(f"Loading quality report from {report_path}...")
    try:
        with open(report_path, 'r', encoding='utf-8') as f:
            report_data = json.load(f)
    except FileNotFoundError:
        print(f"Error: Quality report not found at {report_path}")
        sys.exit(1)
    
    # Report structure assumption: dict where keys are filenames or a list of dicts
    # Adjusting to common patterns. If it's a dict keyed by filename:
    # { "file1.jpg": { "valid": true, "blur": { "score": 0.9 } }, ... }
    # specific structure isn't fully defined in prompt, assuming a dict mapping or list.
    # Let's assume it's a dict keyed by filename for O(1) lookup.
    
    # If report is a dict with 'results' key (common pattern), use that
    if isinstance(report_data, dict) and 'results' in report_data and isinstance(report_data['results'], list):
        report_data = report_data['results']

    # If report is a list, convert to dict keyed by filename
    if isinstance(report_data, list):
         # assuming list of objects with 'filename' key
         report_map = {item.get('filename'): item for item in report_data}
    else:
        report_map = report_data

    assets = []
    source_path = Path(source_dir)
    
    print(f"Scanning source directory {source_dir}...")
    # Extensions to look for
    valid_exts = {'.jpg', '.jpeg', '.png', '.webp'}
    
    for file_path in source_path.iterdir():
        if file_path.suffix.lower() not in valid_exts:
            continue
            
        filename = file_path.name
        
        # Check if in report
        report_entry = report_map.get(filename)
        if not report_entry:
            # Try matching without extension if report keys are just names
            report_entry = report_map.get(file_path.stem)
        
        # If still not found, check if user provided full path in report vs filename
        if not report_entry:
             # Skip if technically not in report? Or assume default? 
             # Prompt says "Sort by blur.score from report", so entry is needed.
             # We will skip valid check if not in report strictly, but better to skip file.
             continue

        # Load caption
        caption_path = file_path.with_suffix('.json')
        caption_data = {}
        if caption_path.exists():
            try:
                with open(caption_path, 'r', encoding='utf-8') as cf:
                    caption_data = json.load(cf)
            except json.JSONDecodeError:
                print(f"Warning: Corrupt JSON for {filename}, skipping arguments from caption.")
        
        assets.append({
            'path': file_path,
            'filename': filename,
            'report': report_entry,
            'caption': caption_data
        })
        
    return assets

def get_bucket(caption_data):
    """Determines the bucket based on caption data."""
    # Priority: camera.distance -> framing -> default 'other'
    # Prompt logic: close_up, upper_body, full_body, other
    
    tags = []
    
    # Helper to check nested keys safely
    def get_val(data, path):
         keys = path.split('.')
         curr = data
         for k in keys:
             if isinstance(curr, dict):
                 curr = curr.get(k)
             else:
                 return None
         return curr

    dist = get_val(caption_data, 'camera.distance')
    framing = get_val(caption_data, 'framing')
    
    focus = get_val(caption_data, 'camera.focus')

    # Normalize input
    val_to_check = str(dist).lower() if dist else (str(framing).lower() if framing else "")
    focus_check = str(focus).lower() if focus else ""
    
    # 0. Check focus for full body override
    if 'full body' in focus_check:
        return 'full-body'
        
    if 'close-up' in val_to_check or 'closeup' in val_to_check or 'head' in val_to_check:
        return 'close-up'
    elif 'upper' in val_to_check or 'mid' in val_to_check or 'medium' in val_to_check: # upper_body or mid_shot or medium shot
        return 'upper-body'
    elif 'full' in val_to_check or 'long' in val_to_check or 'wide' in val_to_check:
        return 'full-body'
    else:
        return 'other'

def filter_assets(assets, target_character=None):
    """Filters assets based on validity and optional character."""
    valid_assets = []
    for asset in assets:
        # 1. Validity Check
        # Report might store valid as boolean or string "true"/"false"
        is_valid = asset['report'].get('valid', False) 
        if isinstance(is_valid, str):
            is_valid = is_valid.lower() == 'true'
        
        if not is_valid:
            continue
            
        # 2. Character Check
        if target_character:
            char_tag = asset['caption'].get('character')
            # Assuming character could be a string or list
            if not char_tag:
                 # If character required but missing from caption, check strictness. 
                 # Usually strict. Skip.
                 continue
            
            target_lower = target_character.lower()
            if isinstance(char_tag, list):
                # Check strict membership (case-insensitive)
                if not any(c.lower() == target_lower for c in char_tag):
                    continue
            else:
                # Check strict equality (case-insensitive)
                if str(char_tag).lower() != target_lower:
                    # Fallback: if it's a comma-separated string?
                    # "Aria, Other"
                    tags = [t.strip().lower() for t in str(char_tag).split(',')]
                    if target_lower not in tags:
                        continue
                    
        valid_assets.append(asset)
    return valid_assets

def score_assets(assets):
    """Extracts score for sorting."""
    # Assuming report structure: { ..., "blur": { "score": 0.8 }, ... }
    # Or top level "score". Adjust based on standard tools.
    # Prompt says: "quality_report içindeki blur.score"
    for asset in assets:
        blur_data = asset['report'].get('blur', {})
        # Handle cases where blur might be the score itself or a dict
        if isinstance(blur_data, (int, float)):
             score = float(blur_data)
        else:
             score = float(blur_data.get('score', 0.0))
        
        asset['final_score'] = score
    return assets

def run_selector(source, report, target, count, dist_str, character=None, force=False, face_target=0):
    """
    Main logic for selecting assets.
    Returns:
        tuple: (success_bool, message_str, report_content_str)
    """
    # 0. Path Safety
    target_path = Path(target)
    if target_path.exists():
        if any(target_path.iterdir()):
            if force:
                print(f"Warning: Target {target} not empty. Force enabled, existing files may be overwritten.")
            else:
                msg = f"Error: Target {target} is not empty. Use --force to allow writing."
                print(msg)
                return False, msg, ""
    else:
        target_path.mkdir(parents=True, exist_ok=True)

    # 1. Parse Distribution
    # Note: parse_distribution exits on error. We might want to change that later, 
    # but for now we catch exceptions in the UI if possible or let it print.
    # To make it library-safe, let's wrap it here.
    try:
        distribution = parse_distribution(dist_str)
    except SystemExit:
         return False, "Error parsing distribution string.", ""
    except Exception as e:
         return False, f"Error parsing distribution string: {e}", ""

    print(f"Target Distribution: {distribution}")

    # 2. Load Data
    try:
        raw_assets = load_data(source, report)
    except SystemExit:
        return False, "Error loading data (report not found or invalid).", ""
        
    print(f"Loaded {len(raw_assets)} valid-format assets from source.")

    # 3. Filter
    filtered_assets = filter_assets(raw_assets, character)
    print(f"Assets after hard filters (validity/char): {len(filtered_assets)}")
    
    if not filtered_assets:
        msg = "No assets remained after filtering."
        print(msg)
        return False, msg, ""

    # 4. Bucketing & Scoring
    scored_assets = score_assets(filtered_assets)
    buckets = defaultdict(list)
    
    for asset in scored_assets:
        b = get_bucket(asset['caption'])
        buckets[b].append(asset)

    # Sort buckets by score desc
    for b in buckets:
        buckets[b].sort(key=lambda x: x['final_score'], reverse=True)
        print(f"Bucket '{b}': {len(buckets[b])} items")

    # 5. Selection Logic
    final_selection = []
    
    # Calculate target counts per bucket using simple rounding
    goals = {}
    for k, v in distribution.items():
        goals[k] = int(round(count * v))
    
    # Adjust for rounding errors (ensure sum matches count)
    current_total = sum(goals.values())
    diff = count - current_total
    
    if diff != 0:
        keys = list(goals.keys())
        target_key = max(goals, key=goals.get) if goals else keys[0]
        goals[target_key] += diff

    # First pass: try to meet goals
    remaining_pool = [] 
    
    for b_name in distribution.keys(): # Iterate defined buckets
        available = buckets.get(b_name, [])
        goal = goals.get(b_name, 0)
        
        # Take up to goal
        taken = available[:goal]
        final_selection.extend(taken)
        
        # Add leftovers to pool
        remaining_pool.extend(available[goal:])
        
        # If we took less than goal, we have a deficit
        deficit = goal - len(taken)
        if deficit > 0:
            print(f"Warning: Bucket '{b_name}' underflow by {deficit}. Will fill from other high-quality assets.")
            
    # Add undefined buckets to pool (e.g. 'other' if not in distribution)
    for b_name in buckets:
        if b_name not in distribution:
            remaining_pool.extend(buckets[b_name])
            
    # Sort remaining pool globally by score
    remaining_pool.sort(key=lambda x: x['final_score'], reverse=True)
    
    # Fill deficit
    needed = count - len(final_selection)
    if needed > 0:
        filled = remaining_pool[:needed]
        final_selection.extend(filled)
        print(f"Filled {len(filled)} spots from general pool.")

    print(f"Final selection count before face check: {len(final_selection)}")
    
    # 5.5 Face Visible Constraint Check & Swap
    # Helper to check face
    def check_face(asset):
        fv = asset['caption'].get('face', {}).get('visible')
        return str(fv).lower() == 'true' if fv is not None else False

    if face_target > 0:
        current_faces = sum(1 for a in final_selection if check_face(a))
        print(f"Current face visible count: {current_faces} (Target: {face_target})")
        
        if current_faces < face_target:
            needed = face_target - current_faces
            print(f"Need {needed} more face-visible assets. Attempting swap...")
            
            # Candidates to remove: specific bucket items without face, low score first
            # Candidates to add: items in remaining pool WITH face, high score first
            
            # Map selection by bucket for safer removal
            sel_by_bucket = defaultdict(list)
            for a in final_selection:
                sel_by_bucket[get_bucket(a['caption'])].append(a)
            
            # Sort pool by score desc
            remaining_pool.sort(key=lambda x: x['final_score'], reverse=True)
            pool_face_candidates = [a for a in remaining_pool if check_face(a)]
            
            swapped_count = 0
            
            # Try to swap within same bucket first to preserve distribution
            for candidate in pool_face_candidates[:]: # Copy to iterate safely if we modify list
                if needed <= 0: break
                
                cand_bucket = get_bucket(candidate['caption'])
                
                # Look for a non-face item in the same bucket in selection to swap out
                # Sort by score ascending (remove worst)
                options = [a for a in sel_by_bucket[cand_bucket] if not check_face(a)]
                options.sort(key=lambda x: x['final_score'])
                
                if options:
                    to_remove = options[0] # Lowest score non-face item in same bucket
                    
                    # Perform Swap
                    final_selection.remove(to_remove)
                    sel_by_bucket[cand_bucket].remove(to_remove)
                    
                    final_selection.append(candidate)
                    sel_by_bucket[cand_bucket].append(candidate)
                    
                    pool_face_candidates.remove(candidate) # consumed
                    remaining_pool.remove(candidate) # consumed from main pool too
                    
                    needed -= 1
                    swapped_count += 1
            
            # Phase 2: If still needed, swap from ANY bucket (sacrificing distribution for face target)
            if needed > 0:
                print(f"Phase 1 swap done. Still need {needed}. Swapping across buckets...")
                # Global list of removable (non-face) sorted by score asc
                removable = [a for a in final_selection if not check_face(a)]
                removable.sort(key=lambda x: x['final_score'])
                
                for candidate in pool_face_candidates:
                    if needed <= 0 or not removable: break
                    
                    to_remove = removable.pop(0) # Lowest score non-face globally
                    
                    final_selection.remove(to_remove)
                    final_selection.append(candidate)
                    
                    needed -= 1
                    swapped_count += 1
                    
            print(f"Swap complete. Total swapped: {swapped_count}. New face count: {sum(1 for a in final_selection if check_face(a))}")

    # 6. Execution
    print("Copying files...")
    success_count = 0
    
    # For report
    selection_stats = defaultdict(int)
    total_score = 0
    
    for asset in final_selection:
        src_img = asset['path']
        dst_img = target_path / asset['filename']
        
        try:
            shutil.copy2(src_img, dst_img)
            
            # Copy caption if exists
            src_cap = src_img.with_suffix('.json')
            if src_cap.exists():
                shutil.copy2(src_cap, target_path / src_cap.name)
            
            success_count += 1
            bucket = get_bucket(asset['caption']) # recalculate/retrieve
            selection_stats[bucket] += 1
            total_score += asset['final_score']
            
        except OSError as e:
            print(f"Error copying {src_img}: {e}")

    # 7. Reporting
    avg_score = total_score / success_count if success_count > 0 else 0
    report_lines = [
        "# Golden Set Selection Report",
        f"- **Total Selected**: {success_count} / {count}",
        f"- **Average Quality Score**: {avg_score:.4f}",
        "",
        "## Distribution Breakdown"
    ]
    
    face_count = sum(1 for a in final_selection if check_face(a))
    report_lines.append(f"- **Total Face Visible**: {face_count} (Target Min: {face_target})")
    
    for b, count_val in selection_stats.items():
        goal = goals.get(b, 0)
        available = len(buckets.get(b, []))
        report_lines.append(f"- **{b}**: {count_val} (Target: {goal}, Available: {available})")
        
    report_file = target_path / "selection_report.md"
    report_content = '\n'.join(report_lines)
    reasons_list = []
    for asset in final_selection:
         b = get_bucket(asset['caption'])
         reasons_list.append(f"- **{asset['filename']}**: {b} (Score: {asset['final_score']})")

    report_content = report_content + "\n\n## Selected Files Detail\n" + '\n'.join(reasons_list)
    with open(report_file, 'w') as f:
        f.write(report_content)
        
    print(f"Done. Report saved to {report_file}")
    return True, f"Successfully selected {success_count} assets.", report_content

def main():
    parser = argparse.ArgumentParser(description="Universal Asset Selector (Golden Set Generator)")
    parser.add_argument('--source', required=True, help="Source directory containing images and captions")
    parser.add_argument('--report', required=True, help="Path to quality_report.json")
    parser.add_argument('--target', required=True, help="Target directory for selected assets")
    parser.add_argument('--count', type=int, required=True, help="Total number of files to select")
    parser.add_argument('--dist', required=True, help="Distribution map (e.g., 'close-up:0.3,upper-body:0.3...')")
    parser.add_argument('--character', help="Target character name for filtering")
    parser.add_argument('--force', action='store_true', help="Force overwrite of target directory")

    args = parser.parse_args()
    
    success, msg, _ = run_selector(args.source, args.report, args.target, args.count, args.dist, args.character, args.force, 0)
    if not success:
        sys.exit(1)

if __name__ == "__main__":
    main()
