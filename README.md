# Youtube Searcher/Recommender

This is a port of https://github.com/chris-lovejoy/YouTube-video-finder that runs
on AWS Lambda.  It's powered by the [AWS Chalice](https://aws.github.io/chalice/)
framework to both help configure as well as deploy the application to AWS.

See the [original article](https://towardsdatascience.com/i-created-my-own-youtube-algorithm-to-stop-me-wasting-time-afd170f4ca3a)
for more details, but as a high-level overview, it will use the recommended
scoring algorithm in the linked article to send you weekly email reports
of the highest ranking youtube videos.

This project will deploy two AWS Lambdas.  One Lambda function can be can run
on demand to allow you to get immediate results using the scored rankings.
The other Lambda function is scheduled to run once a week that generates
a report of your youtube videos and emails them to you.


# Deploying to AWS

This project uses [AWS Chalice](https://aws.github.io/chalice/) to both
write and deploy the application.  You'll need to have Python 3.8 installed
in order to use this.  Or more specifically, this was only tested on Python
3.8.

## Configuring your dev environment

```
# First, verify the python version is 3.8.

$ python3 --version
Python 3.8.5

# Next create a virtual environment.
$ python3 -m venv venv37
$ . venv37/bin/activate
```

Next, you'll need to intall Chalice and other required dependencies.

```
# Requirements used during development
$ pip install -r requirements-dev.txt

# Requirements used at application runtime
$ pip install -r requirements.txt
```

## Configuring the application

Next you'll need to configure the application.  First, open the
`.chalice/config.json` file and replace the `REPORT_EMAIL_ADDRESS` and the
`REPORT_SEARCH_TERMS` with your own values.  The `REPORT_SEARCH_TERMS` is a
comma separated string of search terms that will be used to find youtube
videos.  The `REPORT_EMAIL_ADDRESS` is where the weekly report will be sent.

## Configuring the Youtube API key

You'll need to generate a Youtube v3 API Key
[here](https://console.developers.google.com/cloud-resource-manager).
You can watch [this video](https://www.youtube.com/watch?v=-QMg39gK624) for a
walkthrough on how to do this.

Once you've created your Youtub API key, run the `./configure-api-key` command.


```
$ ./configure-api-key
Enter Youtube API Key:
```

This will securely store your Youtube API key using the
[AWS SSM Parameter
Store](https://docs.aws.amazon.com/systems-manager/latest/userguide/systems-manager-parameter-store.html).
We do this because, as a best practice, we want to avoid hardcoding our API key
in our code as well as not including our API key in our Lambda package.

## Verifying your Email address

If you've never used SES before, it's likely you're in a sandbox which will
require you to verify your email address before you can use SES.  You can
follow the instructions [here](https://docs.aws.amazon.com/ses/latest/DeveloperGuide/verify-email-addresses-procedure.html)
on how to do this.  Be sure to verify the same email address you configured
in `REPORT_EMAIL_ADDRESS`.  You only have to do this once for your AWS
account.

## Deploying your application

You can now deploy your application to AWS.  You should have a `chalice`
command line too installed (which was created when you `pip install`'d the
various requirement files.  From the top level directory, run the `chalice
deploy` command.


```
$ chalice deploy
Creating deployment package.
Creating IAM role: youtube-searcher-dev-on_demand_search
Creating lambda function: youtube-searcher-dev-on_demand_search
Creating IAM role: youtube-searcher-dev-weekly_report
Creating lambda function: youtube-searcher-dev-weekly_report
Resources deployed:
  - Lambda ARN: arn:aws:lambda:us-west-2:12345:function:youtube-searcher-dev-on_demand_search
  - Lambda ARN: arn:aws:lambda:us-west-2:12345:function:youtube-searcher-dev-weekly_report
```

Whenever you make changes to your Chalice application whether it's source code
updates or changes to your `.chalice/config.json`, you can rerun the `chalice
deploy` command and Chalice will update your application on AWS.


## Testing the application

Your application's now deployed, you'll start receiving weekly emails
for youtube videos.

In the meantime, you can try to invoke one of the Lambda functions manually
to verify that all the permissions and configurations were set up correctly.
To to this we'll use the `chalice invoke` command.  You can run the
following command, but replace the keyword value with your own search term.


```
$ echo '{"keyword": "cooking recipes"}' | chalice invoke -n on_demand_search | python -m json.tool
[
    {
        "title": "Restaurant Style Matar Panner Recipe | Miniature Cooking | Chapathi + Matar panner | Mini Food",
        "video_url": "https://www.youtube.com/watch?v=sXxa5loQmr8",
        "view_count": 12099478,
        "score": 1592036.5789473683
    },
    {
        "title": "10 Minutes Recipe - Quick &amp; Easy Breakfast Recipe",
        "video_url": "https://www.youtube.com/watch?v=UIl_5rpi2lI",
        "view_count": 11679113,
        "score": 1191746.224489796
    },
...
```

If you see a JSON document with a list of Youtube videos then congratulations,
everything's working!
