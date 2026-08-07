import subprocess
import sys
import time

def main():
    print("Starting supervised batch extraction (Parts 1-17)...")
    t_start = time.time()
    
    parts = list(range(1, 18))
        
    for part in parts:
        print(f"\n================================================================================")
        print(f"  SUPERVISOR: Launching extraction for Part {part}")
        print(f"================================================================================")
        
        cmd = [
            sys.executable,
            "apps/api/extract_all_penn.py",
            str(part)
        ]
        
        try:
            result = subprocess.run(cmd, check=True)
            print(f"SUPERVISOR: Part {part} finished successfully.")
        except subprocess.CalledProcessError as e:
            print(f"SUPERVISOR: ERROR running Part {part}: {e}")
            
    print(f"\nAll requested parts completed in {time.time() - t_start:.1f}s.")

if __name__ == "__main__":
    main()
