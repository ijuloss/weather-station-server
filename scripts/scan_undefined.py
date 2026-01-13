"""Scan Python files for names that are used but not defined or imported.
Produces a simple report (false positives possible).
"""
import ast
import os
import builtins
ROOT = os.path.dirname(os.path.dirname(__file__))
ignore_dirs = {'.git','node_modules','.history','venv','env','__pycache__','docker','frontend'}

builtin_names = set(dir(builtins))
common_ok = {
    'logger','config','Path','datetime','timezone','json','os','sys','socketio','app','weather_ai',
    'local_data','request','jsonify','isinstance','str','int','float','print','socket','hashlib','np',
    'joblib','Counter','random','requests','firebase_admin','credentials','db','emit','disconnect','emit'
}

results = {}
for dirpath, dirnames, filenames in os.walk(ROOT):
    dirnames[:] = [d for d in dirnames if d not in ignore_dirs]
    for fn in filenames:
        if not fn.endswith('.py'):
            continue
        path = os.path.join(dirpath, fn)
        # skip some large or third-party-like folders
        if '/.history/' in path.replace('\\','/'):
            continue
        try:
            src = open(path, 'r', encoding='utf-8').read()
            tree = ast.parse(src, filename=path)
        except Exception as e:
            results[path] = [f"PARSE_ERROR: {e}"]
            continue

        used = set()
        defined = set()
        imports = set()

        class V(ast.NodeVisitor):
            def visit_Name(self,node):
                if isinstance(node.ctx, ast.Load):
                    used.add(node.id)
                else:
                    defined.add(node.id)
                self.generic_visit(node)
            def visit_Import(self,node):
                for n in node.names:
                    asn = n.asname if n.asname else n.name.split('.')[0]
                    defined.add(asn)
                    imports.add(asn)
            def visit_ImportFrom(self,node):
                for n in node.names:
                    asn = n.asname if n.asname else n.name
                    defined.add(asn)
                    imports.add(asn)
            def visit_FunctionDef(self,node):
                defined.add(node.name)
                for a in node.args.args + node.args.kwonlyargs:
                    defined.add(a.arg)
                if node.args.vararg:
                    defined.add(node.args.vararg.arg)
                if node.args.kwarg:
                    defined.add(node.args.kwarg.arg)
                self.generic_visit(node)
            def visit_ClassDef(self,node):
                defined.add(node.name)
                self.generic_visit(node)
            def visit_For(self,node):
                def collect_targets(t):
                    if isinstance(t, ast.Name): defined.add(t.id)
                    elif isinstance(t, (ast.Tuple, ast.List)):
                        for e in t.elts: collect_targets(e)
                collect_targets(node.target)
                self.generic_visit(node)
            def visit_With(self,node):
                for item in node.items:
                    if item.optional_vars and isinstance(item.optional_vars, ast.Name):
                        defined.add(item.optional_vars.id)
                self.generic_visit(node)
            def visit_AnnAssign(self,node):
                t = node.target
                if isinstance(t, ast.Name): defined.add(t.id)
                self.generic_visit(node)
            def visit_Assign(self,node):
                for t in node.targets:
                    if isinstance(t, ast.Name): defined.add(t.id)
                    elif isinstance(t, (ast.Tuple,ast.List)):
                        for e in t.elts:
                            if isinstance(e, ast.Name): defined.add(e.id)
                self.generic_visit(node)
        V().visit(tree)
        candidates = sorted(n for n in (used - defined - builtin_names) if not n.startswith('_'))
        filtered = [n for n in candidates if n not in common_ok]
        if filtered:
            results[path] = filtered

# Print report
if not results:
    print('No suspicious undefined names found.')
else:
    print('Potential undefined names (false positives possible):')
    for p,names in results.items():
        print('\nFILE:', p)
        for n in names:
            print('  -', n)
