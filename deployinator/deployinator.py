from fabric.api import *
from fabric.contrib.project import rsync_project
from fabric.contrib.files import upload_template
import os

# env.user = "ubuntu"
# env.hosts = ["%s@feedify.movieos.org"%USER]

env.user = "tomi"

TEMPLATES = os.path.dirname(__file__)

def fab_init(name, **args):
    env.project = name
    env.rules = {}
    for k, v in args.items():
        setattr(env, k, v)

    env.user = args.get("user", "tomi")
    env.host = args.get("host", "seatbelt.movieos.org")
    env.hosts = ["%(user)s@%(host)s"%env]
    env.deploy = "/home/%s/deploy/%s"%(env.user, name)
    env.venv = "/home/%s/deploy/venv_%s"%(env.user, name)
    env.log = "/var/log/%(project)s"%env



def shell(*cmd):
    import subprocess
    run = ["ssh", "-A", "-t", env.host_string]
    run += cmd
    print ' '.join(run)
    subprocess.call(run)

def manage(cmd=""):
    shell("%(venv)s/bin/python %(deploy)s/manage.py "%env + cmd)

def tail():
    shell("tail -f %(log)s/*.log"%env)

def upgrade():
    sudo("apt-get update")
    sudo("apt-get dist-upgrade")

def sync():
    rsync_project(
        local_dir="./",
        remote_dir="%(deploy)s/"%env,
        exclude=["venv", "*.pyc", ".git"],
        #delete=True,
    )


def deploy():
    run("mkdir -p %(deploy)s"%env)

    # this is just a default baseline list of packages I want on everything. Includes
    # reuqirements for deployment and useful things I just like to have on a server.
    # Preserving order here is important!
    packages = [
        "python", "python-virtualenv", "python-mysqldb",
        "mysql-server", "memcached", "mysql-client", "python-dev",
        "nginx", "joe", "munin", "munin-node", "redis-server", "varnish",
        "python-imaging", "rsync", "screen", "htop", "curl", "git", "build-essential",
    ] + getattr(env, "packages", [])

    sudo("DEBIAN_FRONTEND=noninteractive apt-get update -qq -y")
    sudo("DEBIAN_FRONTEND=noninteractive apt-get install -qq -f -y %s"%(" ".join(packages)), shell=True)

    run("if [ ! -f %(venv)s/bin/python ]; then virtualenv %(venv)s; fi"%env)

    sudo("mkdir -p %(log)s"%env)
    sudo("chown -R %(user)s:%(user)s %(log)s"%env)

    if hasattr(env, "database"):
        run("(echo 'create database %(database)s charset=utf8' | mysql -uroot) || true"%env)

    sync()

    if env.rules.get("nginx"):
        upload_template(env.rules.get("nginx"), "/etc/nginx/sites-enabled/%(project)s.conf"%env,
            use_sudo=True, context=env, backup=False)
        sudo("/etc/init.d/nginx configtest && /etc/init.d/nginx reload")

    if env.rules.get("varnish"):
        upload_template(env.rules.get("varnish"), "/etc/varnish/default.vcl",
            use_sudo=True, context=env, backup=False)
        # sudo('sudo varnishadm "ban.url ."') # flush cache
        sudo("/etc/init.d/varnish restart")

    if os.path.exists("requirements.txt"):
        run("%(venv)s/bin/pip install -q -r %(deploy)s/requirements.txt"%env)

    if env.rules.get("gunicorn"):
        sudo("mkdir -p /var/run/gunicorn")
        context = env.copy()
        context["port"] = str(env.rules["gunicorn"].get("port", 8000))
        context["settings"] = str(env.rules["gunicorn"].get("settings", "settings"))
        upload_template(os.path.join(TEMPLATES, "gunicorn.conf.tmpl"), "/etc/init/%(project)s_gunicorn.conf"%env,
            context=context, use_sudo=True, template_dir=TEMPLATES)
        upload_template(os.path.join(TEMPLATES, "gunicorn.sh.tmpl"), "%(deploy)s/gunicorn.sh"%env,
            context=context, mode=0755, template_dir=TEMPLATES)
        sudo("stop %(project)s_gunicorn; sleep 1; start %(project)s_gunicorn"%env)
        run("cd %(deploy)s && %(venv)s/bin/python manage.py migrate"%env)

    if env.rules.get("cpan"):
        for module in env.rules["cpan"]:
            sudo("cpan %s"%module)

    if env.rules.get("upstart"):
        for script in env.rules["upstart"]:
            upload_template(script+".conf", "/etc/init/%s.conf"%script, use_sudo=True, context=env)
            sudo("stop %s && sleep 1 && start %s"%(script, script))

    if env.rules.get("celery"):
        upload_template(os.path.join(TEMPLATES, "celery.conf.tmpl"), "/etc/init/%(project)s_celery.conf"%env,
            context=context, use_sudo=True, template_dir=TEMPLATES)
        upload_template(os.path.join(TEMPLATES, "celery.sh.tmpl"), "%(deploy)s/celery.sh"%env,
            context=context, template_dir=TEMPLATES, mode=0755)
        sudo("stop %(project)s_celery; sleep 1; start %(project)s_celery"%env)

    if env.rules.get("templates"):
        for name, path in env.rules["templates"].items():
            # TODO - make sudo optional
            upload_template(name, path, context=env, use_sudo=True, mirror_local_mode=True)


    if env.rules.get("extra"):
        for extra in env.rules["extra"]:
            extra()




def get_database():
    run("mysqldump -uroot %(database)s | gzip -c > /tmp/dump.sql.gz"%env, shell=False)
    get("/tmp/dump.sql.gz", "/tmp/%(project)s-dump.sql.gz"%env)
    os.system("echo 'drop database %(database)s;' | mysql -uroot"%env)
    os.system("echo 'create database %(database)s charset=utf8' | mysql -uroot"%env)
    os.system("gzip -cd /tmp/%(project)s-dump.sql.gz | mysql -uroot %(database)s"%env)

