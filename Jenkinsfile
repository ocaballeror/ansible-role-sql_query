pipeline {
    agent any
    environment {
        PATH="/opt/python3/bin:${env.PATH}"
    }
    stages {
        stage('Setup') {
            steps {
                script{
                    // Delete .tox if the requirements files have changed since the last build
                    try {
                        sh """
                        if [ -n "$GIT_COMMIT" ] && [ -n "$GIT_PREVIOUS_COMMIT" ]; then
                            git diff --exit-code -s "$GIT_COMMIT" "$GIT_PREVIOUS_COMMIT" -- requirements*.txt setup.py || rm -rf .tox
                        fi
                        """
                    } catch(_) {}
                }
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
