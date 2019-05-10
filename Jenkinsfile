pipeline {
	agent any
	stages {
		stage('Setup') {
			steps {
				sh "pip install --user --upgrade pytest flake8 pycodestyle"
			}
		}
		stage('Lint') {
			steps {
				sh "flake8 --select=E,F,W,N,B,B902,T"
			}
		}
		stage('Test') {
			steps {
				ansiColor('xterm') {
					sh "pytest -v --color=yes"
				}
			}
		}
	}
}
