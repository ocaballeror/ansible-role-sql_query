pipeline {
    agent any
    environment {
        PATH="/opt/python3/bin:${env.PATH}"
    }
    stages {
        stage('Setup') {
            steps {
                sh "pip install --upgrade tox"
            }
        }
        stage('Lint') {
            steps {
                sh "tox -e lint2,lint3"
            }
        }
        stage('Docs') {
            steps {
                sh "tox -e docs"
            }
        }
        stage('Test') {
            steps {
                ansiColor('xterm') {
                    sh "rm -f .coverage"
                    sh "tox -e py2,py3"
                }
            }
        }
    }
}
