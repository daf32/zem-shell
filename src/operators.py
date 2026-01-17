import json
import os

class OperatorValue:
    def __init__(self, value):
        self.value = value
    
    def __str__(self):
        return self.value

class Operators:
    _config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config.json"))
    _defaults = {
        "input": ">>>", 
        "variable": "$", 
        "pipe": "|", 
        "quote": "'", 
        "double_quote": '"', 
        "space": " ", 
        "semicolon": ";", 
        "comment": "#", 
        "redirect_output": ">", 
        "redirect_input": "<", 
        "background": "&", 
        "variable_start": "{", 
        "variable_end": "}", 
        "escape": "\\"
    }
    
    if not os.path.exists(_config_path):
        try:
            with open(_config_path, "w") as f:
                json.dump({"operators": _defaults}, f, indent=4)
        except Exception:
            pass

    try:
        with open(_config_path, "r") as f:
            _data = json.load(f).get("operators", {})
    except (FileNotFoundError, json.JSONDecodeError):
        _data = _defaults

    input = OperatorValue(_data.get("input", _defaults["input"]))
    variable = OperatorValue(_data.get("variable", _defaults["variable"]))
    pipe = OperatorValue(_data.get("pipe", _defaults["pipe"]))
    quote = OperatorValue(_data.get("quote", _defaults["quote"]))
    double_quote = OperatorValue(_data.get("double_quote", _defaults["double_quote"]))
    space = OperatorValue(_data.get("space", _defaults["space"]))
    semicolon = OperatorValue(_data.get("semicolon", _defaults["semicolon"]))
    comment = OperatorValue(_data.get("comment", _defaults["comment"]))
    redirect_output = OperatorValue(_data.get("redirect_output", _defaults["redirect_output"]))
    redirect_input = OperatorValue(_data.get("redirect_input", _defaults["redirect_input"]))
    background = OperatorValue(_data.get("background", _defaults["background"]))
    variable_start = OperatorValue(_data.get("variable_start", _defaults["variable_start"]))
    variable_end = OperatorValue(_data.get("variable_end", _defaults["variable_end"]))
    escape = OperatorValue(_data.get("escape", _defaults["escape"]))
    
    