"""One Registry-derived computation contract, shared by plan and TaskStore."""
import math
from .working_memory import clone, encoded, NUMERIC_TOOLS
from .working_memory_lifecycle import EVENT_TOOLS


def computation_scope(registry, name):
    schema=clone(registry.get('create_epochs' if name in EVENT_TOOLS else name).parameters)
    if name in EVENT_TOOLS:
        schema['properties']={k:v for k,v in schema['properties'].items() if k in {'labels','tmin','tmax'}}
    schema.update(required=[],additionalProperties=False)
    return schema


def scope_groups(registry):
    groups={}
    for name in sorted(NUMERIC_TOOLS):
        schema=computation_scope(registry,name)
        group=groups.setdefault(encoded(schema),{'names':[],'schema':schema})
        group['names'].append(name)
    return list(groups.values())


class ContractError(ValueError):
    def __init__(self,path,message):
        self.path=list(path)
        super().__init__(message)


def selected_contract(schema, value):
    """Resolve only an explicit enum discriminator, never scientific intent."""
    if 'oneOf' not in schema:
        return schema
    selected = [s for s in schema['oneOf'] if isinstance(value, dict) and any(
        k in value and value[k] in p.get('enum', []) for k, p in s.get('properties', {}).items())]
    return selected[0] if len(selected) == 1 else None


def contract_diagnostics(value, schema, *, limit=24, visit_limit=4096):
    """Bounded aggregate of determinable public representation errors.

    Truncation is explicit and disqualifies diagnostic-count progress. The
    original validator remains authoritative; this function never normalizes.
    """
    issues=[]; seen=set(); visits=0; truncated=False
    def add(path, rule, message):
        nonlocal truncated
        identity=(tuple(path), rule, message)
        if identity in seen:return
        seen.add(identity)
        if len(issues)>=limit:truncated=True;return
        issues.append({'path':list(path),'rule':rule,'message':message})
    def walk(v,s,path=()):
        nonlocal visits,truncated
        visits+=1
        if visits>visit_limit:truncated=True;return
        if 'oneOf' in s:
            chosen=selected_contract(s,v)
            if chosen is None:
                try:validate_contract(v,{'oneOf':s['oneOf']},path)
                except ContractError as e:add(e.path,'oneOf',str(e))
            else:walk(v,chosen,path)
        for sub in s.get('allOf',[]):walk(v,sub,path)
        if 'if' in s:
            try:validate_contract(v,s['if'],path)
            except ContractError:pass
            else:walk(v,s.get('then',{}),path)
        for key in ('type','enum','not','minItems','maxItems','uniqueItems','minLength','maxLength',
                    'minimum','maximum','exclusiveMinimum','exclusiveMaximum'):
            if key not in s:continue
            try:validate_contract(v,{key:s[key]},path)
            except ContractError as e:
                add(e.path,key,str(e))
                if key=='type':return
        if isinstance(v,dict):
            props=s.get('properties',{})
            for key in s.get('required',[]):
                if key not in v:add((*path,key),'required','Required field missing')
            for key,item in v.items():
                if key not in props and s.get('additionalProperties') is False:
                    add((*path,key),'additionalProperties','Unsupported field; allowed: '+', '.join(props))
                elif key in props:walk(item,props[key],(*path,key))
        if isinstance(v,list) and 'items' in s:
            for i,item in enumerate(v):
                if visits>=visit_limit:truncated=True;break
                walk(item,s['items'],(*path,i))
    walk(value,schema)
    return {'issues':issues,'truncated':truncated,'limit':limit}


def validate_contract(value,schema,path=()):
    """Validate the finite JSON-schema vocabulary advertised by DAG controls.

    This checks representation only; metadata, provenance and scientific
    preconditions still belong to the original Store/Executor.
    """
    def fail(message):raise ContractError(path,message)
    types=schema.get('type',[])
    if isinstance(types,str):types=[types]
    predicates={'object':lambda x:isinstance(x,dict),'array':lambda x:isinstance(x,list),
        'string':lambda x:isinstance(x,str),'integer':lambda x:type(x) is int,
        'number':lambda x:type(x) in (int,float) and math.isfinite(x),
        'boolean':lambda x:type(x) is bool,'null':lambda x:x is None}
    if types and not any(predicates[t](value) for t in types):fail('Expected '+' or '.join(types))
    if 'enum' in schema and value not in schema['enum']:fail('Allowed values: '+str(schema['enum']))
    if 'not' in schema:
        try:validate_contract(value,schema['not'],path)
        except ContractError:pass
        else:fail('Conflicting representations are not allowed')
    for sub in schema.get('allOf',[]):validate_contract(value,sub,path)
    if 'if' in schema:
        try:validate_contract(value,schema['if'],path)
        except ContractError:pass
        else:validate_contract(value,schema.get('then',{}),path)
    if 'oneOf' in schema:
        matches=0;errors=[];selected=[]
        for sub in schema['oneOf']:
            try:validate_contract(value,sub,path);matches+=1
            except ContractError as exc:
                errors.append(exc)
                # An explicit enum discriminant can identify the intended
                # representation without inferring any scientific meaning.
                if isinstance(value,dict) and any(k in value and value[k] in p.get('enum',[])
                        for k,p in sub.get('properties',{}).items()):selected.append(exc)
        if matches!=1:
            if matches==0 and len(selected)==1:raise selected[0]
            fail('Choose exactly one advertised representation'+
                 (': '+'; '.join(str(e.path)+': '+str(e) for e in errors) if matches==0 else ''))
    if isinstance(value,dict):
        props=schema.get('properties',{})
        for name in schema.get('required',[]):
            if name not in value:raise ContractError((*path,name),'Required field missing')
        for name,item in value.items():
            if name not in props and schema.get('additionalProperties') is False:
                raise ContractError((*path,name),'Unsupported field; allowed: '+', '.join(props))
            if name in props:validate_contract(item,props[name],(*path,name))
    if isinstance(value,list):
        if not schema.get('minItems',0)<=len(value)<=schema.get('maxItems',float('inf')):fail('Array size outside contract')
        if schema.get('uniqueItems') and len({encoded(v) for v in value})!=len(value):fail('Duplicate array items')
        for i,item in enumerate(value):validate_contract(item,schema.get('items',{}),(*path,i))
    if isinstance(value,str):
        if not schema.get('minLength',0)<=len(value)<=schema.get('maxLength',float('inf')):fail('String length outside contract')
    if type(value) in (int,float):
        if not math.isfinite(value) or not schema.get('minimum',-float('inf'))<=value<=schema.get('maximum',float('inf')):fail('Number outside contract')
        if 'exclusiveMinimum' in schema and value<=schema['exclusiveMinimum']:fail('Number must exceed exclusive minimum')
        if 'exclusiveMaximum' in schema and value>=schema['exclusiveMaximum']:fail('Number must be below exclusive maximum')
