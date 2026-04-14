<<<<<<< HEAD
QGC telemetry dashboard notes


folder

WSL path:
/mnt/c/Users/kudai/OneDrive/Desktop/caltech/qgc-telemetry-dashboard

Windows path:
C:\Users\kudai\OneDrive\Desktop\caltech\qgc-telemetry-dashboard
main idea


Use cleaned QGC telemetry CSV.

Import into Influx.

Open in Grafana.

Show map + speed + heading + relative altitude.



go to repo
cd /mnt/c/Users/kudai/OneDrive/Desktop/caltech/qgc-telemetry-dashboard


docker commands
start in background:

docker compose up -d

see logs if needed:
docker compose logs -f

stop:
docker compose down

full reset if token / setup got messed up:

docker compose down -v
docker compose up -d

open pages
InfluxDB: http://localhost:8086

Grafana: http://localhost:3000



If needed:

cp .env.example .env
Important: same token in both places.

DOCKER_INFLUXDB_INIT_ADMIN_TOKEN

INFLUX_TOKEN


If I change token after containers were already created, I probably need:

docker compose down -v
docker compose up -d
venv


create if needed:

python3 -m venv .venv

turn on:
source .venv/bin/activate

turn off:

deactivate if missing:

sudo apt update
sudo apt install python3-venv -y
install packages inside venv:

python -m pip install -r requirements.txt
env vars for importer


Python importer does not automatically read Docker stuff the way I want, so before running importer I need these in the same terminal:

export INFLUX_ORG=caltech_lab
export INFLUX_BUCKET=qgc_data
export INFLUX_TOKEN=DLJLkCA1ZqRLtFplPcjuPEVPC_67khKtiJPnHv8kRMpOeUEyJS11VxEldzKd1VIfJGcVKoJqjEz8OQFGOfxD2Q==
quick checks:

echo $INFLUX_ORG
echo $INFLUX_BUCKET
echo $INFLUX_TOKEN=DLJLkCA1ZqRLtFplPcjuPEVPC_67khKtiJPnHv8kRMpOeUEyJS11VxEldzKd1VIfJGcVKoJqjEz8OQFGOfxD2Q==
run importer


with venv on and env vars set:

python scripts/import_qgc_telemetry.py




if still weird and repo is fresh, reset:

docker compose down -v
docker compose up -d
then export vars again and rerun importer.



what the columns mean


lat / lon
GPS coordinates in decimal degrees

use for map



heading_deg
compass direction

0 = north, 90 = east, 180 = south, 270 = west

best as line chart over time



speed_xy
cleaned formula is:

sqrt(vx^2 + vy^2) / 100

best as line chart over time



alt_m
meters

came from GLOBAL_POSITION_INT.alt


relative_alt_m
meters

relative to starting / home reference

probably more useful to show than alt_m



best panels



Boat Path map

Speed Over Time

Heading Over Time

Relative Altitude Over Time



grafana queries


speed
from(bucket: "qgc_data")
  |> range(start: 0)
  |> filter(fn: (r) => r._measurement == "qgc_telemetry")
  |> filter(fn: (r) => r.run == "gps_track_cleaned")
  |> filter(fn: (r) => r._field == "speed_xy")
heading
from(bucket: "qgc_data")
  |> range(start: 0)
  |> filter(fn: (r) => r._measurement == "qgc_telemetry")
  |> filter(fn: (r) => r.run == "gps_track_cleaned")
  |> filter(fn: (r) => r._field == "heading_deg")
alt_m
from(bucket: "qgc_data")
  |> range(start: 0)
  |> filter(fn: (r) => r._measurement == "qgc_telemetry")
  |> filter(fn: (r) => r.run == "gps_track_cleaned")
  |> filter(fn: (r) => r._field == "alt_m")
relative_alt_m
from(bucket: "qgc_data")
  |> range(start: 0)
  |> filter(fn: (r) => r._measurement == "qgc_telemetry")
  |> filter(fn: (r) => r.run == "gps_track_cleaned")
  |> filter(fn: (r) => r._field == "relative_alt_m")
map
from(bucket: "qgc_data")
  |> range(start: 0)
  |> filter(fn: (r) => r._measurement == "qgc_telemetry")
  |> filter(fn: (r) => r.run == "gps_track_cleaned")
  |> filter(fn: (r) => r._field == "lat" or r._field == "lon" or r._field == "speed_xy")
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> keep(columns: ["_time", "lat", "lon", "speed_xy"])
Geomap settings:

Visualization = Geomap

Location mode = Coords

Latitude field = lat

Longitude field = lon




Easy fix while building panels:

|> range(start: 0)


This dashboard is from cleaned QGroundControl telemetry.

Map is reconstructed from GPS.

Time series show speed, heading, and vertical position over time.

alt_m is autopilot / GPS reported altitude, not sonar bathymetry depth.



quick workflow reminder


normal session
cd /mnt/c/Users/kudai/OneDrive/Desktop/caltech/qgc-telemetry-dashboard
source .venv/bin/activate
export INFLUX_ORG=caltech_lab
export INFLUX_BUCKET=qgc_data
export INFLUX_TOKEN=my_exact_token_here
docker compose up -d
after changing csv
cd /mnt/c/Users/kudai/OneDrive/Desktop/caltech/qgc-telemetry-dashboard
source .venv/bin/activate
export INFLUX_ORG=caltech_lab
export INFLUX_BUCKET=qgc_data
export INFLUX_TOKEN=my_exact_token_here
python scripts/import_qgc_telemetry.py
finish
docker compose down
deactivate
=======
# qgc-telemetry-dashboard



## Getting started

To make it easy for you to get started with GitLab, here's a list of recommended next steps.

Already a pro? Just edit this README.md and make it your own. Want to make it easy? [Use the template at the bottom](#editing-this-readme)!

## Add your files

* [Create](https://docs.gitlab.com/user/project/repository/web_editor/#create-a-file) or [upload](https://docs.gitlab.com/user/project/repository/web_editor/#upload-a-file) files
* [Add files using the command line](https://docs.gitlab.com/topics/git/add_files/#add-files-to-a-git-repository) or push an existing Git repository with the following command:

```
cd existing_repo
git remote add origin https://gitlab.com/akudaibe-group/qgc-telemetry-dashboard.git
git branch -M main
git push -uf origin main
```

## Integrate with your tools

* [Set up project integrations](https://gitlab.com/akudaibe-group/qgc-telemetry-dashboard/-/settings/integrations)

## Collaborate with your team

* [Invite team members and collaborators](https://docs.gitlab.com/user/project/members/)
* [Create a new merge request](https://docs.gitlab.com/user/project/merge_requests/creating_merge_requests/)
* [Automatically close issues from merge requests](https://docs.gitlab.com/user/project/issues/managing_issues/#closing-issues-automatically)
* [Enable merge request approvals](https://docs.gitlab.com/user/project/merge_requests/approvals/)
* [Set auto-merge](https://docs.gitlab.com/user/project/merge_requests/auto_merge/)

## Test and Deploy

Use the built-in continuous integration in GitLab.

* [Get started with GitLab CI/CD](https://docs.gitlab.com/ci/quick_start/)
* [Analyze your code for known vulnerabilities with Static Application Security Testing (SAST)](https://docs.gitlab.com/user/application_security/sast/)
* [Deploy to Kubernetes, Amazon EC2, or Amazon ECS using Auto Deploy](https://docs.gitlab.com/topics/autodevops/requirements/)
* [Use pull-based deployments for improved Kubernetes management](https://docs.gitlab.com/user/clusters/agent/)
* [Set up protected environments](https://docs.gitlab.com/ci/environments/protected_environments/)

***

# Editing this README

When you're ready to make this README your own, just edit this file and use the handy template below (or feel free to structure it however you want - this is just a starting point!). Thanks to [makeareadme.com](https://www.makeareadme.com/) for this template.

## Suggestions for a good README

Every project is different, so consider which of these sections apply to yours. The sections used in the template are suggestions for most open source projects. Also keep in mind that while a README can be too long and detailed, too long is better than too short. If you think your README is too long, consider utilizing another form of documentation rather than cutting out information.

## Name
Choose a self-explaining name for your project.

## Description
Let people know what your project can do specifically. Provide context and add a link to any reference visitors might be unfamiliar with. A list of Features or a Background subsection can also be added here. If there are alternatives to your project, this is a good place to list differentiating factors.

## Badges
On some READMEs, you may see small images that convey metadata, such as whether or not all the tests are passing for the project. You can use Shields to add some to your README. Many services also have instructions for adding a badge.

## Visuals
Depending on what you are making, it can be a good idea to include screenshots or even a video (you'll frequently see GIFs rather than actual videos). Tools like ttygif can help, but check out Asciinema for a more sophisticated method.

## Installation
Within a particular ecosystem, there may be a common way of installing things, such as using Yarn, NuGet, or Homebrew. However, consider the possibility that whoever is reading your README is a novice and would like more guidance. Listing specific steps helps remove ambiguity and gets people to using your project as quickly as possible. If it only runs in a specific context like a particular programming language version or operating system or has dependencies that have to be installed manually, also add a Requirements subsection.

## Usage
Use examples liberally, and show the expected output if you can. It's helpful to have inline the smallest example of usage that you can demonstrate, while providing links to more sophisticated examples if they are too long to reasonably include in the README.

## Support
Tell people where they can go to for help. It can be any combination of an issue tracker, a chat room, an email address, etc.

## Roadmap
If you have ideas for releases in the future, it is a good idea to list them in the README.

## Contributing
State if you are open to contributions and what your requirements are for accepting them.

For people who want to make changes to your project, it's helpful to have some documentation on how to get started. Perhaps there is a script that they should run or some environment variables that they need to set. Make these steps explicit. These instructions could also be useful to your future self.

You can also document commands to lint the code or run tests. These steps help to ensure high code quality and reduce the likelihood that the changes inadvertently break something. Having instructions for running tests is especially helpful if it requires external setup, such as starting a Selenium server for testing in a browser.

## Authors and acknowledgment
Show your appreciation to those who have contributed to the project.

## License
For open source projects, say how it is licensed.

## Project status
If you have run out of energy or time for your project, put a note at the top of the README saying that development has slowed down or stopped completely. Someone may choose to fork your project or volunteer to step in as a maintainer or owner, allowing your project to keep going. You can also make an explicit request for maintainers.
>>>>>>> 874f13449141597a03cb4c07534c89aaaed8b998
