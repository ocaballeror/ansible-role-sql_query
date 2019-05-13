pipeline {
	agent any
	stages {
		stage('Setup') {
			steps {
				sh "/opt/python3/bin/pip install --upgrade -r requirements_dev.txt"
			}
		}
		stage('Lint') {
			steps {
				sh "ANSIBLE_LIBRARY=library /opt/python3/bin/ansible-doc -t module sql_query"
				sh "/opt/python3/bin/flake8 --select=E,F,W,N,B,B902,T"
			}
		}
		stage('Test') {
			steps {
				ansiColor('xterm') {
					sh "/opt/python3/bin/pytest -v -rs --color=yes"
				}
			}
		}
	}
}
