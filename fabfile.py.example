from fabric.api import run, env, cd, local, hosts

staging_hosts = []
production_hosts = []

env.base_dir = '/srv/project-package'
env.project_dir = 'sublimefabric.py'

@hosts(*staging_hosts)
def reset():
    """ reset DB on staging """
    _manage('reset_staging')
    

@hosts(*staging_hosts)
def stage():
    """ deploy changes on staging """
    local('git push origin master')
    _pull_latest()
    _reload()

@hosts(*production_hosts)
def deploy():
    with cd(env.base_dir):
        _pull_latest()
        _reload()

def _manage(command):
    """ run django management command """
    with cd('{0}/{1}'.format(env.base_dir, env.project_dir)):
        run('./manage.py %s' % command)

def _pull_latest():
    """ pull latest changes from repo """
    with cd(env.base_dir):
        run('git pull')
        run('find . -name "*.pyc" -exec rm {} \;')

def _reload():
    """ reload WSGI server """
    with cd(env.base_dir):
        run('touch conf/run.wsgi')

def create_env(path="./"):
    """ create virtual Python environment for project """
    create_env_dir = u'mkdir {0}env'
    link_project_dir_to_env = u'ln -s {1} {0}env/{1}'
    create_virtualenv = u'virtualenv {0}env'

    command = [create_env_dir, link_project_dir_to_env, create_virtualenv]
    command = u'&&'.join(command).format(path, env.project_dir)
    local(command)
