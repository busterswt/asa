import textwrap, json

def generate_srx_config(ha,data):
    config = '''
version 15.1X49-D50.3;
system {{
    host-name srx;
    root-authentication {{
        encrypted-password "$5$ytpefe9E$XTJpyXsaA9wT0IXXyg4N/xLsnRG2mbMg2MO2WGQCpW0"; ## SECRET-DATA
    }}
    services {{
        ssh;
        web-management {{
            http {{
                interface fxp0.0;
            }}
        }}
    }}
    syslog {{
        user * {{
            any emergency;
        }}
        file messages {{
            any any;
            authorization info;
        }}
        file interactive-commands {{
            interactive-commands any;
        }}
    }}
    license {{
        autoupdate {{
            url https://james.test.net/junos/key_retrieval;
        }}
    }}
}}
security {{
    screen {{
        ids-option untrust-screen {{
            icmp {{
                ping-death;
            }}
            ip {{
                source-route-option;
                tear-drop;
            }}
            tcp {{
                syn-flood {{
                    alarm-threshold 1024;
                    attack-threshold 200;
                    source-threshold 1024;
                    destination-threshold 2048;
                    queue-size 2000; ## Warning: 'queue-size' is deprecated
                    timeout 20;
                }}
                land;
            }}
        }}
    }}
    policies {{
        from-zone trust to-zone trust {{
            policy default-permit {{
                match {{
                    source-address any;
                    destination-address any;
                    application any;
                }}
                then {{
                    permit;
                }}
            }}
        }}
        from-zone trust to-zone untrust {{
            policy default-permit {{
                match {{
                    source-address any;
                    destination-address any;
                    application any;
                }}
                then {{
                    permit;
                }}
            }}
        }}
    }}
    zones {{
        security-zone trust {{
            tcp-rst;
            interfaces {{
                ge-0/0/0.0;
            }}
        }}
        security-zone untrust {{
            screen untrust-screen;
        }}
    }}
}}
interfaces {{
    ge-0/0/0 {{
        unit 0 {{
            family inet {{
                dhcp;
            }}
        }}
    }}
    fxp0 {{
        unit 0 {{
            family inet {{
                dhcp;
            }}
        }}
    }}
}}
	  '''.format(**data)

    return config
