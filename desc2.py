import random

def number_of_interfaces(schema):
    return random.randint(0,1)

def unit_generator_func():
    n = 0
    while True:
        yield str(n)
        n += 1
unit_generator = unit_generator_func()

generator_descriptor = {
    "sys": {
        "interfaces": {
            "interface": {  # name
                "__NO_INSTANCES": (random.randint, 2,3),
                "unit": {  # name
                    "__NO_INSTANCES": (random.randint, 1,20),
                    "name": unit_generator,
                    "status": {
                        "receive": {

                        },
                        "transmit": {
                            "__SKIP": True
                        }
                    },
                    "family": {

                    }
                }
            }
        }
    }
}
