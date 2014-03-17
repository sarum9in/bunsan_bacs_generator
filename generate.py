#!/usr/bin/python3
# -*- coding: utf-8 -*-


import json
import os
from os.path import dirname, join
import subprocess
import sys


keep_going = False
prefix = ''
tests = []
test_destination = '{test}'
environment = {}
imports = [
    'destination',
    'keep_going',
    'prefix',
    'tests',
]


class NonZeroExitStatus(Exception):
    pass


def log_raw(raw):
    print(raw, file=sys.stderr)


def log(format, *args, **kwargs):
    log_raw(format.format(*args, **kwargs))


def log_help():
    log_raw("""
Usage {argv0} --option1 --option2=string-value --no-option3 config1 config2 ...

Options:
    --prefix=path       destination prefix
    --[no-]keep-going   ignore generator's failure

Configuration
=============

JSON object with assigned variables.
User can define any variables that will be used in the code.


Variables
---------
    - 'tests' -- test list
    - 'destination' -- destination template (subject for code evaluation)
    - any command line option

Test list
---------
Test list consists of objects
which can have the following fields:
    - '~' given code is executed, other fields are ignored
    - '^' given code is executed before each test in group
    - '$' given code is executed after each test in group
    - 'integer' given test is created from stdout of given command
    - 'integer,integer,...' multiple test group
    - 'min-max' inclusive test range
    - 'min-max-step' inclusive test range with given step

It is possible to execute arbitrary python code ins

{imports} can't be changed inside test list.

Command substitution
--------------------

{var} can be used inside command, will be replaced by variable
`code` can be used inside command, will be replaced by eval(code)

Code execution
--------------

'~', '^' and '$' accept string or list of strings as value.
Strings are executed in given order by exec().

Example
-------
{
    "destination": "tests/{test:02}.in",
    "x": 50,
    "tests":
    [
        { "1-10": ["echo", "I am {test} test!"] },
        { "11,12": ["echo", "x is `x` for now..."] },
        { "~": "x = 1" },
        {
            "^": "print('I am executed before each test in group, x =', x)",
            "13-20": ["echo", "I am {test} test with x = {x}!"],
            "$":
            [
                "print('I am executed after each test in group')",
                "x *= 1.1"
            ]
        },
        { "~": "print('Finally x is', x)" },
        { "21": ["echo", "Now 2 * x = `2 * x`"] }
    ]
}
    """.strip().replace('{argv0}', sys.argv[0]).replace('{imports}', str(imports)))


def parse_list(tests):
    if type(tests) is list:
        ret = []
        for t in tests:
            ret += parse_list(t)
        return ret
    else:
        lst = tests.split(',')
        assert len(lst) != 0
        if len(lst) == 1:
            rng = list(map(int, lst[0].split('-')))
            if len(rng) == 1:
                return rng
            elif len(rng) == 2:
                return list(range(rng[0], rng[1] + 1))
            else:
                assert len(rng) == 3
                return list(range(rng[0], rng[1] + 1, rng[2]))
        else:
            return parse_list(lst)


def transform(arg):
    arg = str(arg).format(**environment)
    args = arg.split('`')
    assert len(args) % 2 == 1
    args_ = []
    for i in range(len(args)):
        if i % 2 == 0:
            args_.append(args[i])
        else:
            args_.append(str(eval(args[i], environment)))
    return ''.join(args_)


def execute(code):
    if type(code) is list:
        for c in code:
            execute(c)
    else:
        exec(code, environment)


def generate():
    test_list = []
    global tests
    for test_object in tests:
        exec_before = None
        exec_after = None
        if '~' in test_object:
            execute(test_object['~'])
            continue
        if '^' in test_object:
            exec_before = test_object['^']
            del test_object['^']
        if '$' in test_object:
            exec_after = test_object['$']
            del test_object['$']
        lst = list(test_object.items())
        assert len(lst) == 1
        test_, argv = lst[0]
        test_list = parse_list(test_)
        for test in test_list:
            environment['test'] = test
            test_destination = join(prefix, transform(destination))
            if exec_before is not None:
                execute(exec_before)
            try:
                os.makedirs(dirname(test_destination))
            except FileExistsError:
                pass
            with open(test_destination, 'w') as output:
                if type(argv) is list:
                    argv_ = list(map(transform, argv))
                    log('{}: {}', test_destination, ' '.join(argv_))
                    with subprocess.Popen(argv_, stdout=output) as p:
                        if p.wait() != 0:
                            if keep_going:
                                log('[FAILED]')
                            else:
                                raise NonZeroExitStatus(argv_)
                else:
                    src = transform(argv)
                    log('{} = {}', test_destination, src)
                    with open(src) as src_file:
                        output.write(src_file.read())
            if exec_after is not None:
                execute(exec_after)


def opt_name(name):
    return name.replace('-', '_')


def main():
    for i in sys.argv[1:]:
        if i.startswith('--'):
            opt = i[2:]
            if opt == 'help':
                log_help()
                sys.exit()
            eq = opt.find('=')
            if eq == -1:
                if opt.startswith('no-'):
                    environment[opt_name(opt[3:])] = False
                else:
                    environment[opt_name(opt)] = True
            else:
                key = opt_name(opt[:eq])
                value = opt[eq + 1:]
                environment[key] = value
        else:
            log('Using "{}" configuration', i)
            with open(i) as f:
                for key, value in json.load(f).items():
                    environment[key] = value
                for var in imports:
                    if var in environment:
                        globals()[var] = environment[var]
                generate()


if __name__ == '__main__':
    main()
