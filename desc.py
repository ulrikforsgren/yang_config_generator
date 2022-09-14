import random


def gen_name(node):
    # Return None to skip
    return str(random.randint(1, 1000))

def random_number(node):
    return random.randint(1, 10)

def random_speed(node):
    return str(random.randint(1, 1000000))

def gen_number_seq(node):
    n = 100
    while True:
        yield str(n)
        n += 1


generator_descriptor = {
    "router:sys": {
        "interfaces": {
            "interface": {  # name
                "__NO_INSTANCES": random_number,
                "name": gen_name,
                "description": "ulrik",
                "speed": random_speed,
                "enabled": False,
                "unit": {  # name
                    "__NO_INSTANCES": 0,
                    "status": {
                        "receive": {

                        },
                        "transmit": {

                        }
                    },
                    "family": {

                    }
                }
            }
        },
        "routes": {
            "inet": {
                "route": {  # name,prefix-length
                    "next-hop": {  # name
                        "__NO_INSTANCES": 0,
                    }
                }
            },
            "inet6": {
                "route": {  # name,prefix-length
                    "next-hop": {  # name

                    }
                }
            }
        },
        "syslog": {
            "server": {  # name
                "selector": {  # name

                },

            }
        },
        "ntp": {
            "server": {  # name
            },
            "local-clock": {
                "status": {

                }
            },
            "restrict": {  # name,mask

            },
            "key": {  # name

            },

        },
        "dns": {
            "search": {  # name

            },
            "server": {  # address

            },
            "options": {

            }
        },
        "oper": {  # name

        },
        "test": {
            "l2": {

            }
        }
    }
}
