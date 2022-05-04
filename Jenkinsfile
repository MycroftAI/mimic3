// Copyright 2022 Mycroft AI Inc.
//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU Affero General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU Affero General Public License for more details.
//
// You should have received a copy of the GNU Affero General Public License
// along with this program.  If not, see <http://www.gnu.org/licenses/>.
//
// -----------------------------------------------------------------------------
//
// Jenkins pipeline for building Mimic 3 artifacts.
//
// Requires Docker buildx: https://docs.docker.com/buildx/working-with-buildx/
// Assumes the en_UK/apope_low voice is in /home/jenkins/.local/share/mycroft/mimic3/voices

pipeline {
    agent any

    environment {
        // Adds GITHUB_USR and GITHUB_PSW environment variables
        GITHUB = credentials('devops-mycroft')

        DOCKER_BUILDKIT = '1'
        // DOCKER_PLATFORM = 'linux/amd64,linux/arm64,linux/arm/v7'
        DOCKER_PLATFORM = 'linux/amd64'
        DEFAULT_VOICE = 'en_UK/apope_low'
        DEFAULT_VOICE_PATH = '/home/jenkins/.local/share/mycroft/mimic3/voices'

        GITHUB_OWNER = 'mycroftAI'
        GITHUB_REPO = 'mimic3'

        TAG_NAME = 'release/v0.2.0'
    }

    stages {
        // Clean up
        stage('Clean') {
            steps {
                sh 'rm -rf dist/'
            }
        }

        // Clone the source code from Github
        stage('Clone') {
            steps {
                git branch: 'master',
                    credentialsId: 'devops-mycroft',
                    url: 'https://github.com/mycroftAI/mimic3.git'

                // Mycroft TTS plugin
                dir('plugin-tts-mimic3') {
                    git branch: 'master',
                        credentialsId: 'devops-mycroft',
                        url: 'https://github.com/mycroftAI/plugin-tts-mimic3'
                }
            }
        }

        // Copy default voice
        stage('Copy voices') {
            steps {
                sh 'mkdir -p voices/${DEFAULT_VOICE}'
                sh 'rsync -r --link-dest="${DEFAULT_VOICE_PATH}/${DEFAULT_VOICE}/" "${DEFAULT_VOICE_PATH}/${DEFAULT_VOICE}/" voices/${DEFAULT_VOICE}/'
            }
        }

        // Build, test, and publish plugin distribution package to PyPI
        // stage('Plugin dist') {
        //     steps {
        //         sh 'make plugin-dist'
        //     }
        // }

        // Build, test, and publish source distribution packages to PyPI
        stage('Dist') {
            steps {
                sh 'make dist'
            }
        }

        // Create a new tagged Github release with source distribution and Debian packages
        stage('Publish dist') {
            // when {
            //     tag 'release/v*.*.0'
            // }

            environment {
                MIMIC3_VERSION = readFile(file: 'mimic3_tts/VERSION').trim()
            }

            steps {
                // Delete release for tag, if it exists
                sh 'scripts/delete-tagged-release.sh ${GITHUB_OWNER} ${GITHUB_REPO} ${TAG_NAME} ${GITHUB_PSW}'

                // Create new tagged release and upload assets
                sh 'scripts/create-tagged-release.sh ${GITHUB_OWNER} ${GITHUB_REPO} ${TAG_NAME} ${GITHUB_PSW} dist/mycroft_mimic_tts-${MIMIC3_VERSION}.tar.gz application/gzip'
            }

            // Create a new release for tag

            // Upload release assets
        }

        // Build and publish multi-platform Docker image to Dockerhub
        // stage('Docker') {
        //     steps {
        //         sh 'make docker'
        //       //sh 'make docker-gpu'
        //     }
        // }


        // Build and publish Debian packages to Github
        // stage('Debian') {
        //     steps {
        //         sh 'make debian'
        //     }
        // }
    }
}
