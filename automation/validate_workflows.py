"""Parse YAML and syntax-check embedded shell/Python; no workflow execution."""
from pathlib import Path
import re
import subprocess
import textwrap
import yaml

def main():
    for path in Path(".github/workflows").glob("*.yml"):
        data=yaml.load(path.read_text(encoding="utf-8"),Loader=yaml.BaseLoader)
        assert "on" in data and "jobs" in data,path
        for job in data["jobs"].values():
            for step in job.get("steps",[]):
                script=step.get("run")
                if not script:
                    continue
                # Expressions are evaluated by Actions, not shell/Python syntax.
                script=re.sub(r"\$\{\{.*?\}\}","EXPRESSION",script)
                subprocess.run(["bash","-n"],input=script,text=True,check=True)
                for block in re.findall(r"python - <<'PY'\n(.*?)\nPY(?:\n|$)",script,re.S):
                    compile(block,str(path),"exec")
        print("Workflow syntax valid:",path)
if __name__=="__main__":
    main()


