import importlib
import inspect
import sys


def load_directory(directory):
  br = "\\n"
  return f"""for filename in split(globpath('{directory}', '*.vim'), '{br}')
  execute 'source' filename
endfor"""

# '/home/dylan/.vim/plugged/AirLatex.vim/rplugin/python3/airlatex', [
def get_plugin_spec(path, module_name):
  sys.path.insert(0, f'{path}/rplugin/python3')

  module = importlib.import_module(module_name)
  output = []

  for name, obj in inspect.getmembers(module):
    if inspect.isclass(obj):
      if getattr(obj, '_nvim_plugin', False):
        for method_name, method_obj in inspect.getmembers(obj):
          if inspect.isfunction(method_obj):
            rpc_spec = getattr(method_obj, '_nvim_rpc_spec', None)
            if rpc_spec is not None:
              # replacement is a little brittle, but will do for our case.
              output.append(f'{rpc_spec}'.replace("False", "v:false").replace("True", "v:true"))
    return output

def main():
  if len(sys.argv) != 3:
    print("Usage: python script.py <path> <module_name>")
    sys.exit(1)

  path = sys.argv[1]
  module_name = sys.argv[2]

  print(load_directory(f"{path}/plugin"))
  print(load_directory(f"{path}/syntax"))

  output = ["call remote#host#RegisterPlugin('python3'", f"'{path}/rplugin/python3/{module_name}'"]
  methods = get_plugin_spec(path, module_name)
  methods[0] = f"[{methods[0]}"
  methods[-1] = f"{methods[-1]}])"
  print(',\n    \\ '.join(output + methods))

if __name__ == '__main__':
  main()
