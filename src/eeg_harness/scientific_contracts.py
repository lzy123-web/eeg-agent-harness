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
        matches=0
        for sub in schema['oneOf']:
            try:validate_contract(value,sub,path);matches+=1
            except ContractError:pass
        if matches!=1:fail('Choose exactly one advertised representation')
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
        for i,item in enumerate(value):validate_contract(item,schema.get('items',{}),(*path,i))
    if isinstance(value,str):
        if not schema.get('minLength',0)<=len(value)<=schema.get('maxLength',float('inf')):fail('String length outside contract')
    if type(value) in (int,float):
        if not math.isfinite(value) or not schema.get('minimum',-float('inf'))<=value<=schema.get('maximum',float('inf')):fail('Number outside contract')
        if 'exclusiveMinimum' in schema and value<=schema['exclusiveMinimum']:fail('Number must exceed exclusive minimum')
        if 'exclusiveMaximum' in schema and value>=schema['exclusiveMaximum']:fail('Number must be below exclusive maximum')
