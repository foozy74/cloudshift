# Monkeypatch inspect.formatargspec for Python 3.11+ compatibility
import inspect

if not hasattr(inspect, "formatargspec"):
    def formatannotation(annotation, base_module=None):
        if getattr(annotation, '__module__', None) == 'typing':
            return repr(annotation).replace('typing.', '')
        if isinstance(annotation, type):
            if annotation.__module__ in ('builtins', base_module):
                return annotation.__qualname__
            return annotation.__module__ + '.' + annotation.__qualname__
        return repr(annotation)

    def formatargspec(args, varargs=None, varkw=None, defaults=None,
                      kwonlyargs=(), kwonlydefaults={}, annotations={},
                      formatarg=str,
                      formatvarargs=lambda name: '*' + name,
                      formatvarkw=lambda name: '**' + name,
                      formatvalue=lambda value: '=' + repr(value),
                      formatreturns=lambda text: ' -> ' + text,
                      formatannotation=formatannotation):
        """Format an argument spec from getfullargspec values."""
        specs = []
        if args:
            firstdefault = len(args) - len(defaults) if defaults else len(args)
            for i, arg in enumerate(args):
                spec = formatarg(arg)
                if arg in annotations:
                    spec += ': ' + formatannotation(annotations[arg])
                if defaults and i >= firstdefault:
                    spec += formatvalue(defaults[i - firstdefault])
                specs.append(spec)
        if varargs is not None:
            spec = formatvarargs(varargs)
            if varargs in annotations:
                spec += ': ' + formatannotation(annotations[varargs])
            specs.append(spec)
        elif kwonlyargs:
            specs.append('*')
        if kwonlyargs:
            for arg in kwonlyargs:
                spec = formatarg(arg)
                if arg in annotations:
                    spec += ': ' + formatannotation(annotations[arg])
                if kwonlydefaults and arg in kwonlydefaults:
                    spec += formatvalue(kwonlydefaults[arg])
                specs.append(spec)
        if varkw is not None:
            spec = formatvarkw(varkw)
            if varkw in annotations:
                spec += ': ' + formatannotation(annotations[varkw])
            specs.append(spec)
        result = '(' + ', '.join(specs) + ')'
        if 'return' in annotations:
            result += formatreturns(formatannotation(annotations['return']))
        return result

    inspect.formatargspec = formatargspec
