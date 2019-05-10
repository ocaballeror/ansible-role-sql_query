pipeline {
	agent any
	stages {
		stage('Setup') {
			steps {
				sh "pip install --user --upgrade pytest"
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
