import os

NOTE = '''"""HyperScale Platform

Architectural Note (Senior Dev):
    This package acts as a boundary context for the microservice. Exposing internal
    modules explicitly via __all__ (where applicable) prevents namespace pollution
    and enforces strict dependency boundaries. In distributed systems, keeping
    domain boundaries airtight prevents unintended coupling that can lead to cascading
    failures across independent deployments.
"""
'''

def update_init_files():
    count = 0
    for root, dirs, files in os.walk('.'):
        # Skip virtualenvs or hidden dirs if they exist
        if 'venv' in root or '.git' in root or '__pycache__' in root:
            continue
        for file in files:
            if file == '__init__.py':
                path = os.path.join(root, file)
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                if 'Architectural Note (Senior Dev)' not in content and len(content) < 200:
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(NOTE)
                    count += 1
    print(f"Updated {count} __init__.py files.")

if __name__ == "__main__":
    update_init_files()
