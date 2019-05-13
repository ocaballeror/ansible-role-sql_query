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
				// Verify module documentation
				sh "/opt/python3/bin/ansible-lint ."
				// Lint ansible
				sh "ANSIBLE_LIBRARY=library /opt/python3/bin/ansible-doc -t module sql_query"
				// Lint python code
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
