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
// Assumes the en_UK/apope_low voice is in /home/jenkins/.local/share/mimic3/voices

pipeline {
    agent any

    environment {
        // https://docs.docker.com/buildx/working-with-buildx/
        DOCKER_BUILDKIT = '1'

        // x86_64, ARM 32/64-bit
        DOCKER_PLATFORM = 'linux/amd64,linux/arm64,linux/arm/v7'

        // https://github.com/MycroftAI/mimic3-voices/tree/master/voices/en_UK/apope_low
        DEFAULT_VOICE = 'en_UK/apope_low'


        // git clone https://github.com/MycroftAI/mimic3-voices.git /home/jenkins/.local/share/mimic3
        // requires git-lfs (https://git-lfs.github.com/)
        DEFAULT_VOICE_PATH = '/home/jenkins/.local/share/mimic3/voices'
    }

    stages {
        // Clone the source code from Github
        stage('Clone') {
            steps {
                git branch: 'master',
                    credentialsId: 'devops-mycroft',
                    url: 'https://github.com/MycroftAI/mimic3.git'

            }
        }

        // Copy default voice
        stage('Copy voice') {
            steps {
                sh 'mkdir -p voices/${DEFAULT_VOICE}'
                sh 'rsync -r --link-dest="${DEFAULT_VOICE_PATH}/${DEFAULT_VOICE}/" "${DEFAULT_VOICE_PATH}/${DEFAULT_VOICE}/" voices/${DEFAULT_VOICE}/'
            }
        }

        // Build and publish source distribution packages to PyPI
        stage('Dist') {
            steps {
                sh 'make dist'
            }
        }

        // TODO: Mycroft Plugin

        // Build and publish multi-platform Docker image to Dockerhub
        stage('Docker') {
            steps {
                sh 'make docker'
                //sh 'make docker-gpu'
            }
        }


        // Build and publish Debian packages to Github
        stage('Debian') {
            steps {
                sh 'make debian'
            }
        }
    }
}
