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
                    sh """
                    rm -rf .coverage .coverage.* reports
                    mkdir -p reports
                    tox -e py2 -- --junitxml=reports/report_py2.xml
                    tox -e py3 -- --junitxml=reports/report_py3.xml
                    """
                }
            }
            post {
                always {
                    junit "reports/*"
                }
            }
        }
    }
}
